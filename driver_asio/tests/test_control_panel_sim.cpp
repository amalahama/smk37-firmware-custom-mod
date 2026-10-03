#include <windows.h>
#include <stdio.h>
#include "iasiodrv.h"

static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

static IASIO* g_pAsio = NULL;

static void bufferSwitch(long doubleBufferIndex, ASIOBool directProcess) {}
static ASIOTime* bufferSwitchTimeInfo(ASIOTime* params, long doubleBufferIndex, ASIOBool directProcess) { return params; }
static void sampleRateChanged(ASIOSampleRate sRate) {}

static long asioMessages(long selector, long value, void* message, double* opt) {
    printf("[HOST asioMessage] selector=%ld, value=%ld\n", selector, value);
    if (selector == 1) { // kAsioResetRequest
        printf("[HOST asioMessage] kAsioResetRequest received! Simulating Ableton reset...\n");
        // Ableton calls stop(), disposeBuffers(), createBuffers(), start()
        if (g_pAsio) {
            printf("  Host calling stop()...\n");
            g_pAsio->stop();
            printf("  Host calling disposeBuffers()...\n");
            g_pAsio->disposeBuffers();
            printf("  Host reset simulation completed.\n");
        }
    }
    return 1;
}

static ASIOCallbacks g_callbacks = {
    bufferSwitch,
    sampleRateChanged,
    asioMessages,
    bufferSwitchTimeInfo
};

int main() {
    CoInitialize(NULL);
    printf("=== Simulating Ableton Live Control Panel Interaction ===\n");

    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                  IID_IASIO, (void**)&g_pAsio);
    if (FAILED(hr) || !g_pAsio) {
        printf("CoCreateInstance failed: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    g_pAsio->init(NULL);

    ASIOBufferInfo bInfos[4] = { 0 };
    bInfos[0].isInput = 1; bInfos[0].channelNum = 0;
    bInfos[1].isInput = 1; bInfos[1].channelNum = 1;
    bInfos[2].isInput = 0; bInfos[2].channelNum = 0;
    bInfos[3].isInput = 0; bInfos[3].channelNum = 1;

    g_pAsio->createBuffers(bInfos, 4, 64, &g_callbacks);
    g_pAsio->start();

    printf("Driver started. Now opening control panel...\n");
    // Launch a thread that will close the control panel dialog after 1 second by clicking OK
    HANDLE hThread = CreateThread(NULL, 0, [](LPVOID) -> DWORD {
        Sleep(800);
        HWND hWnd = FindWindowW(L"SMK37Pro_ASIO_ControlPanel", NULL);
        if (hWnd) {
            printf("Found Control Panel window: %p. Simulating user clicking OK (IDOK)...\n", hWnd);
            HWND hCombo = GetDlgItem(hWnd, 102);
            SendMessageW(hCombo, CB_SETCURSEL, 4, 0); // select 512
            HWND hChk = GetDlgItem(hWnd, 103);
            SendMessageW(hChk, BM_SETCHECK, BST_UNCHECKED, 0); // uncheck
            PostMessageW(hWnd, WM_COMMAND, MAKEWPARAM(IDOK, BN_CLICKED), (LPARAM)GetDlgItem(hWnd, IDOK));
        } else {
            printf("Control Panel window not found!\n");
        }
        return 0;
    }, NULL, 0, NULL);

    printf("Calling g_pAsio->controlPanel()...\n");
    g_pAsio->controlPanel();
    printf("[OK] controlPanel() returned successfully!\n");

    WaitForSingleObject(hThread, 2000);
    CloseHandle(hThread);

    g_pAsio->stop();
    g_pAsio->disposeBuffers();
    g_pAsio->Release();
    CoUninitialize();
    printf("=== Test completed successfully ===\n");
    return 0;
}
