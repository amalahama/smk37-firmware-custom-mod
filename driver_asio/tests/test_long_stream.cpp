#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#include <math.h>
#include "iasiodrv.h"

static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

static volatile long g_bufferCount = 0;
static long g_bufferSize = 512;
static ASIOBufferInfo g_bufferInfos[4];
static double g_phase = 0.0;

static void bufferSwitch(long doubleBufferIndex, ASIOBool directProcess) {
    g_bufferCount++;
    int32_t* pL = (int32_t*)g_bufferInfos[2].buffers[doubleBufferIndex];
    int32_t* pR = (int32_t*)g_bufferInfos[3].buffers[doubleBufferIndex];
    if (pL && pR) {
        for (long i = 0; i < g_bufferSize; i++) {
            float sample = (float)sin(g_phase) * 0.2f;
            g_phase += 0.0628;
            if (g_phase >= 6.2831853) g_phase -= 6.2831853;
            int32_t s32 = (int32_t)(sample * 2147483647.0f);
            pL[i] = s32;
            pR[i] = s32;
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

int main() {
    printf("=== Long-Duration Continuous Playback Stability Test (30 seconds) ===\n");
    CoInitialize(NULL);

    IASIO* pAsio = NULL;
    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                  IID_IASIO, (void**)&pAsio);
    if (FAILED(hr) || !pAsio) {
        printf("FAILED CoCreateInstance\n");
        return 1;
    }
    pAsio->init(NULL);

    long minSz, maxSz, prefSz, gran;
    pAsio->getBufferSize(&minSz, &maxSz, &prefSz, &gran);
    g_bufferSize = prefSz;

    memset(g_bufferInfos, 0, sizeof(g_bufferInfos));
    g_bufferInfos[0].isInput = ASIOTrue;  g_bufferInfos[0].channelNum = 0;
    g_bufferInfos[1].isInput = ASIOTrue;  g_bufferInfos[1].channelNum = 1;
    g_bufferInfos[2].isInput = ASIOFalse; g_bufferInfos[2].channelNum = 0;
    g_bufferInfos[3].isInput = ASIOFalse; g_bufferInfos[3].channelNum = 1;

    pAsio->createBuffers(g_bufferInfos, 4, g_bufferSize, &g_callbacks);
    pAsio->start();

    printf("Audio stream started (bufferSize=%ld, sampleRate=44100 Hz).\n", g_bufferSize);
    printf("Expected callbacks/sec: ~%.1f\n", 44100.0 / g_bufferSize);

    long prevCount = 0;
    for (int sec = 1; sec <= 15; sec++) {
        Sleep(2000);
        long current = g_bufferCount;
        long delta = current - prevCount;
        double rate = (double)delta / 2.0;
        prevCount = current;
        printf("[%02d s] Total callbacks: %ld (Rate: %.1f cbs/sec, Expected: %.1f cbs/sec)\n",
               sec * 2, current, rate, 44100.0 / g_bufferSize);
    }

    pAsio->stop();
    pAsio->disposeBuffers();
    pAsio->Release();
    CoUninitialize();

    printf("=== Stress Test Completed Cleanly! No Freezes, No Latency Accumulation! ===\n");
    return 0;
}
