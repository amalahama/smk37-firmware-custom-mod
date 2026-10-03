#include <windows.h>
#include <stdio.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <functiondiscoverykeys_devpkey.h>
#include <string>
#include <vector>
#include "iasiodrv.h"

static const PROPERTYKEY PKEY_Device_InstanceId_Def = {
    { 0x78c34fc8, 0x104a, 0x4aca, { 0x9e, 0xa4, 0x52, 0x4d, 0x52, 0x99, 0x6e, 0x57 } }, 256
};
static const PROPERTYKEY PKEY_Device_FriendlyName_Def = {
    { 0xa45c254e, 0xdf1c, 0x4efd, { 0x80, 0x20, 0x67, 0xd1, 0x46, 0xa8, 0x50, 0xe0 } }, 14
};
static const PROPERTYKEY PKEY_Device_DeviceDesc_Def = {
    { 0xa45c254e, 0xdf1c, 0x4efd, { 0x80, 0x20, 0x67, 0xd1, 0x46, 0xa8, 0x50, 0xe0 } }, 2
};

static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

int main() {
    CoInitialize(NULL);
    printf("=== Testing Audio Endpoints Enumeration ===\n");

    IMMDeviceEnumerator* pEnum = NULL;
    HRESULT hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                                  __uuidof(IMMDeviceEnumerator), (void**)&pEnum);
    if (FAILED(hr)) {
        printf("Failed to create MMDeviceEnumerator: 0x%08X\n", (unsigned int)hr);
        return 1;
    }

    const char* flowNames[] = { "eRender (Out)", "eCapture (In)" };
    EDataFlow flows[] = { eRender, eCapture };

    for (int f = 0; f < 2; f++) {
        printf("\n--- Flow: %s ---\n", flowNames[f]);
        IMMDeviceCollection* pCol = NULL;
        hr = pEnum->EnumAudioEndpoints(flows[f], DEVICE_STATE_ACTIVE, &pCol);
        if (SUCCEEDED(hr) && pCol) {
            UINT count = 0;
            pCol->GetCount(&count);
            for (UINT i = 0; i < count; i++) {
                IMMDevice* pDev = NULL;
                if (SUCCEEDED(pCol->Item(i, &pDev)) && pDev) {
                    IPropertyStore* pProps = NULL;
                    if (SUCCEEDED(pDev->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
                        PROPVARIANT vName, vDesc, vInst;
                        PropVariantInit(&vName);
                        PropVariantInit(&vDesc);
                        PropVariantInit(&vInst);

                        pProps->GetValue(PKEY_Device_FriendlyName_Def, &vName);
                        pProps->GetValue(PKEY_Device_DeviceDesc_Def, &vDesc);
                        pProps->GetValue(PKEY_Device_InstanceId_Def, &vInst);

                        wprintf(L"  [%u] Name: %s\n", i, vName.pwszVal ? vName.pwszVal : L"<none>");
                        wprintf(L"      Desc: %s\n", vDesc.pwszVal ? vDesc.pwszVal : L"<none>");
                        wprintf(L"      Inst: %s\n", vInst.pwszVal ? vInst.pwszVal : L"<none>");

                        PropVariantClear(&vName);
                        PropVariantClear(&vDesc);
                        PropVariantClear(&vInst);
                        pProps->Release();
                    }
                    pDev->Release();
                }
            }
            pCol->Release();
        }
    }

    printf("\n=== Testing CoCreateInstance like Steinberg / Ableton Live ===\n");
    void* pDriver = NULL;
    hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER, CLSID_SMK37Pro_ASIO, &pDriver);
    printf("CoCreateInstance with RIID=CLSID_SMK37Pro_ASIO result: 0x%08X (%s)\n",
           (unsigned int)hr, SUCCEEDED(hr) ? "SUCCESS" : "FAILED");

    if (SUCCEEDED(hr) && pDriver) {
        IASIO* pAsio = (IASIO*)pDriver;
        printf("\n=== Testing IASIO Driver Methods ===\n");

        ASIOBool initRes = pAsio->init(NULL);
        printf("init(NULL) -> %s\n", initRes == ASIOTrue ? "ASIOTrue" : "ASIOFalse");

        char drvName[64] = {0};
        pAsio->getDriverName(drvName);
        printf("getDriverName -> '%s'\n", drvName);

        long nIn = 0, nOut = 0;
        pAsio->getChannels(&nIn, &nOut);
        printf("getChannels -> Inputs: %ld, Outputs: %ld\n", nIn, nOut);

        long minSz = 0, maxSz = 0, prefSz = 0, gran = 0;
        pAsio->getBufferSize(&minSz, &maxSz, &prefSz, &gran);
        printf("getBufferSize -> Min: %ld, Max: %ld, Pref: %ld, Gran: %ld\n", minSz, maxSz, prefSz, gran);

        ASIOSampleRate sr = 0;
        pAsio->getSampleRate(&sr);
        printf("getSampleRate -> %.0f Hz\n", sr);

        // Test createBuffers
        ASIOBufferInfo bufInfos[4];
        bufInfos[0].isInput = ASIOTrue;  bufInfos[0].channelNum = 0;
        bufInfos[1].isInput = ASIOTrue;  bufInfos[1].channelNum = 1;
        bufInfos[2].isInput = ASIOFalse; bufInfos[2].channelNum = 0;
        bufInfos[3].isInput = ASIOFalse; bufInfos[3].channelNum = 1;

        ASIOCallbacks cbs = { 0 };
        ASIOError bErr = pAsio->createBuffers(bufInfos, 4, prefSz, &cbs);
        printf("createBuffers(4 channels, %ld samples) -> %ld\n", prefSz, bErr);

        ASIOError startErr = pAsio->start();
        printf("start() -> %ld (%s)\n", startErr, startErr == ASE_OK ? "ASE_OK" : "FAILED");

        Sleep(300);

        ASIOError stopErr = pAsio->stop();
        printf("stop() -> %ld\n", stopErr);

        pAsio->disposeBuffers();
        printf("disposeBuffers() -> OK\n");

        pAsio->Release();
    }

    pEnum->Release();
    CoUninitialize();
    return 0;
}
