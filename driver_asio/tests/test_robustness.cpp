#include <windows.h>
#include <stdio.h>
#include <math.h>
#include "iasiodrv.h"

static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

static volatile long g_bufferCount = 0;
static long g_bufferSize = 64;
static ASIOBufferInfo g_bufferInfos[4];

static void bufferSwitch(long doubleBufferIndex, ASIOBool directProcess) {
    InterlockedIncrement(&g_bufferCount);
    int32_t* pL = (int32_t*)g_bufferInfos[2].buffers[doubleBufferIndex];
    int32_t* pR = (int32_t*)g_bufferInfos[3].buffers[doubleBufferIndex];
    if (pL && pR) {
        for (long i = 0; i < g_bufferSize; i++) {
            pL[i] = 0;
            pR[i] = 0;
        }
    }
}

static ASIOTime* bufferSwitchTimeInfo(ASIOTime* params, long doubleBufferIndex, ASIOBool directProcess) {
    bufferSwitch(doubleBufferIndex, directProcess);
    return params;
}

static void sampleRateChanged(ASIOSampleRate sRate) {}
static long asioMessages(long selector, long value, void* message, double* opt) { return 1; }

static ASIOCallbacks g_callbacks = {
    bufferSwitch,
    sampleRateChanged,
    asioMessages,
    bufferSwitchTimeInfo
};

bool testBufferSize(IASIO* pAsio, long bufSize) {
    printf("\n>>> Testing buffer size %ld samples...\n", bufSize);
    g_bufferSize = bufSize;
    g_bufferCount = 0;

    memset(g_bufferInfos, 0, sizeof(g_bufferInfos));
    g_bufferInfos[0].isInput = ASIOTrue;
    g_bufferInfos[0].channelNum = 0;
    g_bufferInfos[1].isInput = ASIOTrue;
    g_bufferInfos[1].channelNum = 1;
    g_bufferInfos[2].isInput = ASIOFalse;
    g_bufferInfos[2].channelNum = 0;
    g_bufferInfos[3].isInput = ASIOFalse;
    g_bufferInfos[3].channelNum = 1;

    ASIOError err = pAsio->createBuffers(g_bufferInfos, 4, bufSize, &g_callbacks);
    if (err != ASE_OK) {
        printf("  [FAIL] createBuffers(%ld) returned %ld\n", bufSize, err);
        return false;
    }

    err = pAsio->start();
    if (err != ASE_OK) {
        printf("  [FAIL] start() returned %ld\n", err);
        pAsio->disposeBuffers();
        return false;
    }

    // Run for 500 ms and check callback progression
    long lastCount = 0;
    int stalledPeriods = 0;
    for (int i = 0; i < 5; i++) {
        Sleep(100);
        long curCount = g_bufferCount;
        long delta = curCount - lastCount;
        printf("    Period %d (100ms): %ld callbacks (total=%ld)\n", i, delta, curCount);
        if (delta == 0) {
            stalledPeriods++;
        }
        lastCount = curCount;
    }

    err = pAsio->stop();
    if (err != ASE_OK) {
        printf("  [FAIL] stop() returned %ld\n", err);
    }

    err = pAsio->disposeBuffers();
    if (err != ASE_OK) {
        printf("  [FAIL] disposeBuffers() returned %ld\n", err);
    }

    if (stalledPeriods > 1) {
        printf("  [WARNING] Stream stalled during test (stalls=%d)!\n", stalledPeriods);
        return false;
    }

    printf("  [PASS] Buffer size %ld passed successfully! Total callbacks=%ld\n", bufSize, g_bufferCount);
    return true;
}

int main() {
    CoInitialize(NULL);
    printf("=== Testing ASIO Buffer Size Robustness & Transitions ===\n");

    IASIO* pAsio = NULL;
    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                  IID_IASIO, (void**)&pAsio);
    if (FAILED(hr) || !pAsio) {
        printf("CoCreateInstance failed: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    if (!pAsio->init(NULL)) {
        printf("pAsio->init failed\n");
        pAsio->Release();
        return 1;
    }

    for (int mode = 0; mode < 2; mode++) {
        bool exclusive = (mode == 0);
        printf("\n=======================================================\n");
        printf("  TESTING MODE: %s\n", exclusive ? "EXCLUSIVE MODE (Ultra-Low Latency)" : "SHARED MODE");
        printf("=======================================================\n");

        HKEY hKey;
        if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\M-VAVE\\SMK-37 Pro ASIO", 0, KEY_WRITE, &hKey) == ERROR_SUCCESS) {
            DWORD dwExcl = exclusive ? 1 : 0;
            RegSetValueExW(hKey, L"ExclusiveMode", 0, REG_DWORD, (const BYTE*)&dwExcl, sizeof(dwExcl));
            RegCloseKey(hKey);
        }

        IASIO* pAsio = NULL;
        HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                      IID_IASIO, (void**)&pAsio);
        if (FAILED(hr) || !pAsio) {
            printf("CoCreateInstance failed: 0x%08X\n", (unsigned int)hr);
            return 1;
        }

        if (!pAsio->init(NULL)) {
            printf("pAsio->init failed\n");
            pAsio->Release();
            return 1;
        }

        long sizes[] = { 32, 64, 128, 256, 512, 1024, 2048 };
        for (long sz : sizes) {
            testBufferSize(pAsio, sz);
        }

        pAsio->Release();
    }
    CoUninitialize();
    printf("\n=== All Tests Finished ===\n");
    return 0;
}
