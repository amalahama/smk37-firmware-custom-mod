#include <windows.h>
#include "iasiodrv.h"

// Unique CLSID for M-VAVE SMK-37 Pro ASIO Driver:
// {7C38B80E-5AED-4B33-A751-6CE34EC4C701}
static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

// Steinberg IASIO Interface GUID:
// {3F484C24-76B8-11D1-8B06-00A024406D59}
static const IID IID_IASIO_LOCAL = {
    0x3f484c24, 0x76b8, 0x11d1, { 0x8b, 0x06, 0x00, 0xa0, 0x24, 0x40, 0x6d, 0x59 }
};

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    CoInitialize(NULL);

    IASIO* pAsio = NULL;
    HRESULT hr = CoCreateInstance(CLSID_SMK37Pro_ASIO, NULL, CLSCTX_INPROC_SERVER,
                                  IID_IASIO_LOCAL, (void**)&pAsio);

    if (SUCCEEDED(hr) && pAsio) {
        if (pAsio->init(NULL)) {
            pAsio->controlPanel();
        }
        pAsio->Release();
    } else {
        MessageBoxW(NULL,
            L"Could not initialize M-VAVE SMK-37 Pro ASIO Driver.\n\nPlease verify that the driver is registered by running install_driver.bat.",
            L"M-VAVE SMK-37 Pro ASIO Control Panel",
            MB_ICONERROR | MB_OK);
    }

    CoUninitialize();
    return 0;
}
