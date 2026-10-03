#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include "iasiodrv.h"

// CLSID: {7C38B80E-5AED-4B33-A751-6CE34EC4C701}
static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

static volatile int s_callbackCount = 0;
static int64_t s_firstSystemTime = 0;
static int64_t s_lastSystemTime = 0;
static int64_t s_firstSamplePos = 0;
static int64_t s_lastSamplePos = 0;

static ASIOTime* bufferSwitchTimeInfo(ASIOTime* params, long doubleBufferIndex, ASIOBool directProcess) {
    if (params) {
        int64_t sysTime = ((int64_t)params->timeInfo.systemTime.hi << 32) | (uint32_t)params->timeInfo.systemTime.lo;
        int64_t sPos = ((int64_t)params->timeInfo.samplePosition.hi << 32) | (uint32_t)params->timeInfo.samplePosition.lo;
        if (s_callbackCount == 0) {
            s_firstSystemTime = sysTime;
            s_firstSamplePos = sPos;
        }
        s_lastSystemTime = sysTime;
        s_lastSamplePos = sPos;
    }
    s_callbackCount++;
    return params;
}

static void bufferSwitch(long doubleBufferIndex, ASIOBool directProcess) {
    s_callbackCount++;
}

static void sampleRateDidChange(ASIOSampleRate sRate) {}

static long asioMessage(long selector, long value, void* message, double* opt) {
    return 0;
}

static ASIOCallbacks g_callbacks = {
    bufferSwitch,
    sampleRateDidChange,
    asioMessage,
    bufferSwitchTimeInfo
};

static inline int64_t GetSystemTimeNanoseconds(const LARGE_INTEGER& qpcFreq) {
    LARGE_INTEGER qpc;
    QueryPerformanceCounter(&qpc);
    if (qpcFreq.QuadPart <= 0) return 0;
    int64_t sec = qpc.QuadPart / qpcFreq.QuadPart;
    int64_t rem = qpc.QuadPart % qpcFreq.QuadPart;
    return (sec * 1000000000LL) + ((rem * 1000000000LL) / qpcFreq.QuadPart);
}

int main() {
    CoInitialize(NULL);
    printf("=== Testing ASIO Timestamp Real System Clock ===\n");

    IASIO* pAsio = NULL;
    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER, CLSID_SMK37Pro_ASIO, (void**)&pAsio);
    if (FAILED(hr) || !pAsio) {
        printf("FAILED CoCreateInstance: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    if (!pAsio->init(NULL)) {
        printf("FAILED init()\n");
        pAsio->Release();
        return 1;
    }

    long minS, maxS, prefS, gran;
    pAsio->getBufferSize(&minS, &maxS, &prefS, &gran);
    printf("getBufferSize: min=%ld, max=%ld, pref=%ld, gran=%ld\n", minS, maxS, prefS, gran);

    ASIOBufferInfo bufInfos[4];
    memset(bufInfos, 0, sizeof(bufInfos));
    bufInfos[0].isInput = ASIOTrue;  bufInfos[0].channelNum = 0;
    bufInfos[1].isInput = ASIOTrue;  bufInfos[1].channelNum = 1;
    bufInfos[2].isInput = ASIOFalse; bufInfos[2].channelNum = 0;
    bufInfos[3].isInput = ASIOFalse; bufInfos[3].channelNum = 1;

    long bufSize = 512;
    if (pAsio->createBuffers(bufInfos, 4, bufSize, &g_callbacks) != ASE_OK) {
        printf("FAILED createBuffers()\n");
        pAsio->Release();
        return 1;
    }

    LARGE_INTEGER qpcFreq;
    QueryPerformanceFrequency(&qpcFreq);
    int64_t beforeNanos = GetSystemTimeNanoseconds(qpcFreq);

    if (pAsio->start() != ASE_OK) {
        printf("FAILED start()\n");
        pAsio->disposeBuffers();
        pAsio->Release();
        return 1;
    }

    Sleep(500);

    int64_t afterNanos = GetSystemTimeNanoseconds(qpcFreq);

    ASIOSamples curPos;
    ASIOTimeStamp curStamp;
    pAsio->getSamplePosition(&curPos, &curStamp);
    int64_t stampNanos = ((int64_t)curStamp.hi << 32) | (uint32_t)curStamp.lo;

    pAsio->stop();
    pAsio->disposeBuffers();
    pAsio->Release();
    CoUninitialize();

    printf("Test duration QPC: before=%lld ns, after=%lld ns (delta = %lld ms)\n",
           beforeNanos, afterNanos, (afterNanos - beforeNanos) / 1000000LL);
    printf("Callback First systemTime=%lld ns, Last systemTime=%lld ns (callbacks=%d)\n",
           s_firstSystemTime, s_lastSystemTime, s_callbackCount);
    printf("getSamplePosition tStamp=%lld ns\n", stampNanos);

    bool ok1 = (s_firstSystemTime >= beforeNanos && s_firstSystemTime <= afterNanos);
    bool ok2 = (stampNanos >= beforeNanos && stampNanos <= (afterNanos + 50000000LL));
    bool ok3 = (gran == -1);

    printf("Check 1: s_firstSystemTime in expected QPC window: %s\n", ok1 ? "PASS" : "FAIL");
    printf("Check 2: getSamplePosition tStamp in expected QPC window: %s\n", ok2 ? "PASS" : "FAIL");
    printf("Check 3: Granularity is -1 (power of two): %s\n", ok3 ? "PASS" : "FAIL");

    if (ok1 && ok2 && ok3) {
        printf("=== ALL TIMESTAMP TESTS PASSED PERFECTLY! ===\n");
        return 0;
    }
    return 1;
}
