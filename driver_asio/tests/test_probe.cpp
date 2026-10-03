#include <windows.h>
#include <stdio.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>
#include <string>
#include <vector>

static const GUID GUID_SUBTYPE_PCM_DEF = {
    0x00000001, 0x0000, 0x0010, { 0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71 }
};

int main() {
    CoInitialize(NULL);
    printf("=== Probing SMK-37 Pro WASAPI Audio Endpoints ===\n");

    IMMDeviceEnumerator* pEnum = NULL;
    HRESULT hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                                  __uuidof(IMMDeviceEnumerator), (void**)&pEnum);
    if (FAILED(hr)) {
        printf("Failed to create MMDeviceEnumerator: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    IMMDeviceCollection* pCol = NULL;
    hr = pEnum->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &pCol);
    if (FAILED(hr) || !pCol) return 1;

    UINT count = 0;
    pCol->GetCount(&count);

    IMMDevice* pSmkDev = NULL;
    for (UINT i = 0; i < count; i++) {
        IMMDevice* pDev = NULL;
        if (SUCCEEDED(pCol->Item(i, &pDev)) && pDev) {
            IPropertyStore* pProps = NULL;
            if (SUCCEEDED(pDev->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
                PROPVARIANT vName;
                PropVariantInit(&vName);
                if (SUCCEEDED(pProps->GetValue(PKEY_Device_FriendlyName, &vName)) && vName.pwszVal) {
                    if (wcsstr(vName.pwszVal, L"SMK") || wcsstr(vName.pwszVal, L"M-VAVE")) {
                        wprintf(L"Found SMK Render Device: %s\n", vName.pwszVal);
                        pSmkDev = pDev;
                        pSmkDev->AddRef();
                        PropVariantClear(&vName);
                        pProps->Release();
                        pDev->Release();
                        break;
                    }
                }
                PropVariantClear(&vName);
                pProps->Release();
            }
            pDev->Release();
        }
    }
    pCol->Release();

    if (!pSmkDev) {
        printf("SMK-37 Pro Render device not found!\n");
        return 1;
    }

    IAudioClient* pClient = NULL;
    hr = pSmkDev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&pClient);
    if (FAILED(hr) || !pClient) {
        printf("Failed to activate IAudioClient: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    REFERENCE_TIME defPeriod = 0, minPeriod = 0;
    hr = pClient->GetDevicePeriod(&defPeriod, &minPeriod);
    printf("GetDevicePeriod: defPeriod = %lld (%.2f ms), minPeriod = %lld (%.2f ms)\n",
           defPeriod, defPeriod / 10000.0, minPeriod, minPeriod / 10000.0);

    WAVEFORMATEX* pMix = NULL;
    hr = pClient->GetMixFormat(&pMix);
    if (SUCCEEDED(hr) && pMix) {
        printf("GetMixFormat: tag=0x%X, ch=%u, rate=%u, bits=%u, blockAlign=%u\n",
               pMix->wFormatTag, pMix->nChannels, (unsigned int)pMix->nSamplesPerSec,
               pMix->wBitsPerSample, pMix->nBlockAlign);
        CoTaskMemFree(pMix);
    }

    printf("\n--- Probing Exclusive Mode Formats ---\n");

    // Test 1: Standard 16-bit 44.1kHz PCM
    WAVEFORMATEX wf16 = { 0 };
    wf16.wFormatTag = WAVE_FORMAT_PCM;
    wf16.nChannels = 2;
    wf16.nSamplesPerSec = 44100;
    wf16.wBitsPerSample = 16;
    wf16.nBlockAlign = 4;
    wf16.nAvgBytesPerSec = 44100 * 4;
    wf16.cbSize = 0;

    WAVEFORMATEX* pClosest = NULL;
    hr = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, &wf16, NULL);
    printf("IsFormatSupported(Exclusive, 16-bit 44.1k PCM): 0x%08X (%s)\n",
           (unsigned int)hr, hr == S_OK ? "SUPPORTED" : "FAILED");

    // Test 2: Standard 16-bit 48kHz PCM
    wf16.nSamplesPerSec = 48000;
    wf16.nAvgBytesPerSec = 48000 * 4;
    hr = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, &wf16, NULL);
    printf("IsFormatSupported(Exclusive, 16-bit 48k PCM): 0x%08X (%s)\n",
           (unsigned int)hr, hr == S_OK ? "SUPPORTED" : "FAILED");

    // Test 3: 24-bit extensible PCM
    WAVEFORMATEXTENSIBLE wfe24 = { 0 };
    wfe24.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
    wfe24.Format.nChannels = 2;
    wfe24.Format.nSamplesPerSec = 44100;
    wfe24.Format.wBitsPerSample = 32;
    wfe24.Format.nBlockAlign = 8;
    wfe24.Format.nAvgBytesPerSec = 44100 * 8;
    wfe24.Format.cbSize = 22;
    wfe24.Samples.wValidBitsPerSample = 24;
    wfe24.dwChannelMask = 3;
    wfe24.SubFormat = GUID_SUBTYPE_PCM_DEF;

    hr = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, (WAVEFORMATEX*)&wfe24, NULL);
    printf("IsFormatSupported(Exclusive, 24-in-32 44.1k PCM Extensible): 0x%08X (%s)\n",
           (unsigned int)hr, hr == S_OK ? "SUPPORTED" : "FAILED");

    // Test 4: Try actual Initialize Exclusive Mode with 16-bit 44.1kHz
    wf16.nSamplesPerSec = 44100;
    wf16.nAvgBytesPerSec = 44100 * 4;
    REFERENCE_TIME hnsReq = minPeriod > 0 ? minPeriod : 100000; // ~10ms or minPeriod
    DWORD flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK;

    hr = pClient->Initialize(AUDCLNT_SHAREMODE_EXCLUSIVE, flags, hnsReq, hnsReq, &wf16, NULL);
    printf("Initialize(Exclusive, 16-bit 44.1k, hns=%lld): 0x%08X (%s)\n",
           hnsReq, (unsigned int)hr, SUCCEEDED(hr) ? "SUCCESS" : "FAILED");

    if (hr == AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED) {
        UINT32 frames = 0;
        pClient->GetBufferSize(&frames);
        printf("  Buffer not aligned! Aligned buffer frames = %u\n", frames);
    }

    pClient->Release();
    pSmkDev->Release();
    pEnum->Release();
    CoUninitialize();
    return 0;
}
