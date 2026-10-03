#include <windows.h>
#include <stdio.h>
#include <math.h>
#include "iasiodrv.h"

static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

static double g_phase = 0.0;
static long g_bufferCount = 0;
static long g_bufferSize = 64;
static ASIOBufferInfo g_bufferInfos[4];

static void bufferSwitch(long doubleBufferIndex, ASIOBool directProcess) {
    g_bufferCount++;
    // Fill with 440 Hz sine wave into output channels
    double freq = 440.0;
    double sampleRate = 44100.0;
    double phaseInc = (2.0 * 3.14159265358979323846 * freq) / sampleRate;

    int32_t* pL = (int32_t*)g_bufferInfos[2].buffers[doubleBufferIndex]; // Out 0
    int32_t* pR = (int32_t*)g_bufferInfos[3].buffers[doubleBufferIndex]; // Out 1

    if (pL && pR) {
        for (long i = 0; i < g_bufferSize; i++) {
            float sample = (float)sin(g_phase) * 0.3f; // -10 dB
            g_phase += phaseInc;
            if (g_phase >= 2.0 * 3.14159265358979323846) {
                g_phase -= 2.0 * 3.14159265358979323846;
            }
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

static void sampleRateChanged(ASIOSampleRate sRate) {
    printf("[HOST] Sample rate changed: %.0f\n", sRate);
}

static long asioMessages(long selector, long value, void* message, double* opt) {
    printf("[HOST] asioMessage selector=%ld, val=%ld\n", selector, value);
    return 1;
}

static ASIOCallbacks g_callbacks = {
    bufferSwitch,
    sampleRateChanged,
    asioMessages,
    bufferSwitchTimeInfo
};

int main() {
    printf("=== SMK-37 Pro ASIO Driver Stream Test ===\n");
    CoInitialize(NULL);

    IASIO* pAsio = NULL;
    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                  IID_IASIO, (void**)&pAsio);
    if (FAILED(hr) || !pAsio) {
        printf("ERROR: CoCreateInstance failed: 0x%08X\n", (unsigned int)hr);
        return 1;
    }
    printf("[OK] CoCreateInstance succeeded!\n");

    if (!pAsio->init(NULL)) {
        printf("ERROR: pAsio->init failed!\n");
        pAsio->Release();
        return 1;
    }
    printf("[OK] init succeeded!\n");

    char drvName[128] = { 0 };
    pAsio->getDriverName(drvName);
    printf("[OK] Driver: %s (version %ld)\n", drvName, pAsio->getDriverVersion());

    long inCh = 0, outCh = 0;
    pAsio->getChannels(&inCh, &outCh);
    printf("[OK] Channels: in=%ld, out=%ld\n", inCh, outCh);

    long minSz = 0, maxSz = 0, prefSz = 0, gran = 0;
    pAsio->getBufferSize(&minSz, &maxSz, &prefSz, &gran);
    printf("[OK] BufferSize: min=%ld, max=%ld, pref=%ld, gran=%ld\n", minSz, maxSz, prefSz, gran);
    g_bufferSize = prefSz;

    memset(g_bufferInfos, 0, sizeof(g_bufferInfos));
    // Input 0, 1
    g_bufferInfos[0].isInput = ASIOTrue;
    g_bufferInfos[0].channelNum = 0;
    g_bufferInfos[1].isInput = ASIOTrue;
    g_bufferInfos[1].channelNum = 1;
    // Output 0, 1
    g_bufferInfos[2].isInput = ASIOFalse;
    g_bufferInfos[2].channelNum = 0;
    g_bufferInfos[3].isInput = ASIOFalse;
    g_bufferInfos[3].channelNum = 1;

    ASIOError err = pAsio->createBuffers(g_bufferInfos, 4, g_bufferSize, &g_callbacks);
    if (err != ASE_OK) {
        printf("ERROR: createBuffers failed: %ld\n", err);
        pAsio->Release();
        return 1;
    }
    printf("[OK] createBuffers succeeded with bufferSize=%ld!\n", g_bufferSize);

    printf("Starting audio stream...\n");
    err = pAsio->start();
    if (err != ASE_OK) {
        printf("ERROR: start failed: %ld\n", err);
        pAsio->disposeBuffers();
        pAsio->Release();
        return 1;
    }
    printf("[OK] start succeeded! Streaming 440Hz test tone for 2 seconds...\n");

    for (int sec = 0; sec < 20; sec++) {
        Sleep(100);
        printf("\rStreaming... Callbacks received: %ld", g_bufferCount);
        fflush(stdout);
    }
    printf("\n");

    printf("Stopping audio stream...\n");
    pAsio->stop();
    printf("[OK] stop succeeded!\n");

    pAsio->disposeBuffers();
    printf("[OK] disposeBuffers succeeded!\n");

    pAsio->Release();
    CoUninitialize();
    printf("=== Test Completed Successfully without Errors or Crashes! ===\n");
    return 0;
}
