#include <windows.h>
#include <unknwn.h>
#include "smk37pro_asio.h"

HINSTANCE g_hInstance = NULL;
static LONG g_serverLocks = 0;

// COM Class Factory Implementation
class CSMK37ProClassFactory : public IClassFactory {
public:
    CSMK37ProClassFactory() : m_refCount(1) {}

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, LPVOID* ppvObj) override {
        if (!ppvObj) return E_POINTER;
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory)) {
            *ppvObj = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppvObj = NULL;
        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override {
        return InterlockedIncrement(&m_refCount);
    }

    STDMETHODIMP_(ULONG) Release() override {
        ULONG count = InterlockedDecrement(&m_refCount);
        if (count == 0) delete this;
        return count;
    }

    // IClassFactory
    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppvObject) override {
        AsioLog("CSMK37ProClassFactory::CreateInstance called");
        if (pUnkOuter != NULL) return CLASS_E_NOAGGREGATION;
        if (!ppvObject) return E_POINTER;

        CSMK37ProASIO* pDriver = new CSMK37ProASIO();
        HRESULT hr = pDriver->QueryInterface(riid, ppvObject);
        pDriver->Release(); // Balance initial refcount
        AsioLog("CSMK37ProClassFactory::CreateInstance -> QueryInterface result: 0x%08X", (unsigned int)hr);
        return hr;
    }

    STDMETHODIMP LockServer(BOOL fLock) override {
        if (fLock) InterlockedIncrement(&g_serverLocks);
        else InterlockedDecrement(&g_serverLocks);
        return S_OK;
    }

private:
    volatile LONG m_refCount;
};

// ---------------------------------------------------------------- DLL Exports
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        g_hInstance = hinstDLL;
        DisableThreadLibraryCalls(hinstDLL);
        AsioLog("DllMain: DLL_PROCESS_ATTACH");
    } else if (fdwReason == DLL_PROCESS_DETACH) {
        AsioLog("DllMain: DLL_PROCESS_DETACH");
    }
    return TRUE;
}

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, LPVOID* ppv) {
    AsioLog("DllGetClassObject called");
    if (!ppv) return E_POINTER;
    *ppv = NULL;

    if (IsEqualCLSID(rclsid, CLSID_SMK37Pro_ASIO)) {
        CSMK37ProClassFactory* pFactory = new CSMK37ProClassFactory();
        HRESULT hr = pFactory->QueryInterface(riid, ppv);
        pFactory->Release();
        AsioLog("DllGetClassObject -> Factory QueryInterface: 0x%08X", (unsigned int)hr);
        return hr;
    }
    AsioLog("DllGetClassObject -> CLASS_E_CLASSNOTAVAILABLE");
    return CLASS_E_CLASSNOTAVAILABLE;
}

STDAPI DllCanUnloadNow() {
    return (g_serverLocks == 0) ? S_OK : S_FALSE;
}

#define CLSID_STR L"{7C38B80E-5AED-4B33-A751-6CE34EC4C701}"
#define ASIO_REG_KEY L"SOFTWARE\\ASIO\\M-VAVE SMK-37 Pro ASIO"
#define ASIO_WOW64_KEY L"SOFTWARE\\WOW6432Node\\ASIO\\M-VAVE SMK-37 Pro ASIO"

STDAPI DllRegisterServer() {
    wchar_t szDllPath[MAX_PATH];
    GetModuleFileNameW(g_hInstance, szDllPath, MAX_PATH);

    HKEY hKey;
    std::wstring clsidPath = L"CLSID\\" CLSID_STR;

    // 1. Register in HKCR\CLSID\{...}
    if (RegCreateKeyExW(HKEY_CLASSES_ROOT, clsidPath.c_str(), 0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, NULL, 0, REG_SZ, (const BYTE*)L"M-VAVE SMK-37 Pro ASIO", sizeof(L"M-VAVE SMK-37 Pro ASIO"));
        
        HKEY hSubKey;
        if (RegCreateKeyExW(hKey, L"InprocServer32", 0, NULL, 0, KEY_WRITE, NULL, &hSubKey, NULL) == ERROR_SUCCESS) {
            RegSetValueExW(hSubKey, NULL, 0, REG_SZ, (const BYTE*)szDllPath, (DWORD)(wcslen(szDllPath) + 1) * sizeof(wchar_t));
            RegSetValueExW(hSubKey, L"ThreadingModel", 0, REG_SZ, (const BYTE*)L"Apartment", sizeof(L"Apartment"));
            RegCloseKey(hSubKey);
        }
        RegCloseKey(hKey);
    }

    // 2. Register in HKLM\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO (mandatory for Ableton Live, Cubase, etc.)
    LONG lRes1 = RegCreateKeyExW(HKEY_LOCAL_MACHINE, ASIO_REG_KEY, 0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL);
    if (lRes1 == ERROR_SUCCESS) {
        RegSetValueExW(hKey, L"CLSID", 0, REG_SZ, (const BYTE*)CLSID_STR, sizeof(CLSID_STR));
        RegSetValueExW(hKey, L"Description", 0, REG_SZ, (const BYTE*)L"M-VAVE SMK-37 Pro ASIO", sizeof(L"M-VAVE SMK-37 Pro ASIO"));
        RegCloseKey(hKey);
    }

    // 2b. Also register in WOW6432Node for 32-bit DAW compatibility
    if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, ASIO_WOW64_KEY, 0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, L"CLSID", 0, REG_SZ, (const BYTE*)CLSID_STR, sizeof(CLSID_STR));
        RegSetValueExW(hKey, L"Description", 0, REG_SZ, (const BYTE*)L"M-VAVE SMK-37 Pro ASIO", sizeof(L"M-VAVE SMK-37 Pro ASIO"));
        RegCloseKey(hKey);
    }

    // 3. Register in HKCU\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO (fallback)
    if (RegCreateKeyExW(HKEY_CURRENT_USER, ASIO_REG_KEY, 0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, L"CLSID", 0, REG_SZ, (const BYTE*)CLSID_STR, sizeof(CLSID_STR));
        RegSetValueExW(hKey, L"Description", 0, REG_SZ, (const BYTE*)L"M-VAVE SMK-37 Pro ASIO", sizeof(L"M-VAVE SMK-37 Pro ASIO"));
        RegCloseKey(hKey);
    }

    // 4. Register in HKCU\Software\Classes\CLSID\{...} (fallback)
    std::wstring hkcuClsid = L"Software\\Classes\\CLSID\\" CLSID_STR;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, hkcuClsid.c_str(), 0, NULL, 0, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, NULL, 0, REG_SZ, (const BYTE*)L"M-VAVE SMK-37 Pro ASIO", sizeof(L"M-VAVE SMK-37 Pro ASIO"));
        HKEY hSubKey;
        if (RegCreateKeyExW(hKey, L"InprocServer32", 0, NULL, 0, KEY_WRITE, NULL, &hSubKey, NULL) == ERROR_SUCCESS) {
            RegSetValueExW(hSubKey, NULL, 0, REG_SZ, (const BYTE*)szDllPath, (DWORD)(wcslen(szDllPath) + 1) * sizeof(wchar_t));
            RegSetValueExW(hSubKey, L"ThreadingModel", 0, REG_SZ, (const BYTE*)L"Apartment", sizeof(L"Apartment"));
            RegCloseKey(hSubKey);
        }
        RegCloseKey(hKey);
    }

    return (lRes1 == ERROR_SUCCESS) ? S_OK : HRESULT_FROM_WIN32(lRes1);
}

STDAPI DllUnregisterServer() {
    RegDeleteKeyW(HKEY_CLASSES_ROOT, L"CLSID\\" CLSID_STR L"\\InprocServer32");
    RegDeleteKeyW(HKEY_CLASSES_ROOT, L"CLSID\\" CLSID_STR);
    RegDeleteKeyW(HKEY_CURRENT_USER, L"Software\\Classes\\CLSID\\" CLSID_STR L"\\InprocServer32");
    RegDeleteKeyW(HKEY_CURRENT_USER, L"Software\\Classes\\CLSID\\" CLSID_STR);
    RegDeleteKeyW(HKEY_LOCAL_MACHINE, ASIO_REG_KEY);
    RegDeleteKeyW(HKEY_LOCAL_MACHINE, ASIO_WOW64_KEY);
    RegDeleteKeyW(HKEY_CURRENT_USER, ASIO_REG_KEY);
    return S_OK;
}
