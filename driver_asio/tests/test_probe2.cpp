#include <windows.h>
#include <stdio.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>

static const GUID SUBTYPE_PCM = {
    0x00000001, 0x0000, 0x0010, { 0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71 }
};
static const GUID SUBTYPE_FLOAT = {
    0x00000003, 0x0000, 0x0010, { 0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71 }
};

int main() {
    CoInitialize(NULL);
    IMMDeviceEnumerator* pEnum = NULL;
    CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                     __uuidof(IMMDeviceEnumerator), (void**)&pEnum);
    if (!pEnum) return 1;

    IMMDeviceCollection* pCol = NULL;
    pEnum->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &pCol);
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
                        wprintf(L"Device: %s\n", vName.pwszVal);
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

    if (!pSmkDev) return 1;

    IAudioClient* pClient = NULL;
    pSmkDev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&pClient);

    WAVEFORMATEX* pMix = NULL;
    pClient->GetMixFormat(&pMix);
    if (pMix) {
        printf("MixFormat: tag=0x%X, ch=%u, rate=%u, bits=%u\n",
               pMix->wFormatTag, pMix->nChannels, (unsigned int)pMix->nSamplesPerSec, pMix->wBitsPerSample);
        if (pMix->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
            WAVEFORMATEXTENSIBLE* pExt = (WAVEFORMATEXTENSIBLE*)pMix;
            printf("  Subformat: {%08lX-...}\n", pExt->SubFormat.Data1);
        }
    }

    printf("\nTesting formats:\n");
    DWORD rates[] = { 44100, 48000 };
    WORD bits[] = { 16, 24, 32 };

    for (DWORD r : rates) {
        for (WORD b : bits) {
            // Standard PCM
            WAVEFORMATEX wf = { 0 };
            wf.wFormatTag = WAVE_FORMAT_PCM;
            wf.nChannels = 2;
            wf.nSamplesPerSec = r;
            wf.wBitsPerSample = b;
            wf.nBlockAlign = (2 * b) / 8;
            wf.nAvgBytesPerSec = r * wf.nBlockAlign;
            wf.cbSize = 0;

            HRESULT hrExcl = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, &wf, NULL);
            HRESULT hrShar = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_SHARED, &wf, NULL);
            printf("  PCM %u Hz, %2u-bit: Excl=0x%08X, Shared=0x%08X\n", (unsigned int)r, b, (unsigned int)hrExcl, (unsigned int)hrShar);

            // Extensible PCM
            WAVEFORMATEXTENSIBLE wfe = { 0 };
            wfe.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
            wfe.Format.nChannels = 2;
            wfe.Format.nSamplesPerSec = r;
            wfe.Format.wBitsPerSample = (b == 24) ? 32 : b;
            wfe.Format.nBlockAlign = (2 * wfe.Format.wBitsPerSample) / 8;
            wfe.Format.nAvgBytesPerSec = r * wfe.Format.nBlockAlign;
            wfe.Format.cbSize = 22;
            wfe.Samples.wValidBitsPerSample = b;
            wfe.dwChannelMask = 3;
            wfe.SubFormat = SUBTYPE_PCM;

            hrExcl = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, (WAVEFORMATEX*)&wfe, NULL);
            hrShar = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_SHARED, (WAVEFORMATEX*)&wfe, NULL);
            printf("  Ext PCM %u Hz, %2u-bit: Excl=0x%08X, Shared=0x%08X\n", (unsigned int)r, b, (unsigned int)hrExcl, (unsigned int)hrShar);

            // Extensible Float (32-bit only)
            if (b == 32) {
                wfe.SubFormat = SUBTYPE_FLOAT;
                hrExcl = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_EXCLUSIVE, (WAVEFORMATEX*)&wfe, NULL);
                hrShar = pClient->IsFormatSupported(AUDCLNT_SHAREMODE_SHARED, (WAVEFORMATEX*)&wfe, NULL);
                printf("  Ext Float %u Hz, %2u-bit: Excl=0x%08X, Shared=0x%08X\n", (unsigned int)r, b, (unsigned int)hrExcl, (unsigned int)hrShar);
            }
        }
    }

    if (pMix) CoTaskMemFree(pMix);
    pClient->Release();
    pSmkDev->Release();
    pEnum->Release();
    CoUninitialize();
    return 0;
}
