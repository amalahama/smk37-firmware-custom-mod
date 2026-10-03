#include "smk37pro_asio.h"
#include <commctrl.h>
#include <shlobj.h>
#include <cmath>
#include <stdio.h>
#include <stdarg.h>

void AsioLog(const char* fmt, ...) {
    static char logPath[MAX_PATH] = { 0 };
    if (logPath[0] == 0) {
        char temp[MAX_PATH];
        if (GetTempPathA(MAX_PATH, temp) > 0) {
            snprintf(logPath, sizeof(logPath), "%ssmk37_asio.log", temp);
        } else {
            strcpy(logPath, "C:\\Users\\amala\\AppData\\Local\\Temp\\smk37_asio.log");
        }
    }
    FILE* f = fopen(logPath, "a");
    if (!f) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(f, "[%02d:%02d:%02d.%03d] ", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);
    fprintf(f, "\n");
    fclose(f);
}

// Static GUID definitions to eliminate dependency on ksmedia.h / uuid linking issues
static const GUID GUID_SUBTYPE_PCM = {
    0x00000001, 0x0000, 0x0010, { 0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71 }
};
static const GUID GUID_SUBTYPE_IEEE_FLOAT = {
    0x00000003, 0x0000, 0x0010, { 0x80, 0x00, 0x00, 0xaa, 0x00, 0x38, 0x9b, 0x71 }
};

// High-precision non-overflowing system wall-clock nanoseconds
static inline int64_t GetWallClockNanoseconds(const LARGE_INTEGER& qpcFreq) {
    if (qpcFreq.QuadPart <= 0) return 0;
    LARGE_INTEGER qpc;
    QueryPerformanceCounter(&qpc);
    int64_t sec = qpc.QuadPart / qpcFreq.QuadPart;
    int64_t rem = qpc.QuadPart % qpcFreq.QuadPart;
    return (sec * 1000000000LL) + ((rem * 1000000000LL) / qpcFreq.QuadPart);
}

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "avrt.lib")
#pragma comment(lib, "comctl32.lib")

// Global DLL Module instance
extern HINSTANCE g_hInstance;

CSMK37ProASIO::CSMK37ProASIO()
    : m_refCount(1),
      m_initialized(false),
      m_running(false),
      m_hParentWnd(NULL),
      m_bufferSize(DEFAULT_BUFFER_SIZE),
      m_pendingBufferSize(DEFAULT_BUFFER_SIZE),
      m_allocatedBufferSize(0),
      m_sampleRate(DEFAULT_SAMPLE_RATE),
      m_exclusiveMode(true),
      m_detectedDevName(L"Searching..."),
      m_deviceFound(false),
      m_numChannels(0),
      m_bufferInfos(NULL),
      m_callbacks(NULL),
      m_doubleBufferIndex(0),
      m_samplePosition(0),
      m_pEnumerator(NULL),
      m_pRenderDevice(NULL),
      m_pCaptureDevice(NULL),
      m_pRenderClient(NULL),
      m_pCaptureClient(NULL),
      m_pRenderService(NULL),
      m_pCaptureService(NULL),
      m_hRenderEvent(NULL),
      m_hCaptureEvent(NULL),
      m_hStopEvent(NULL),
      m_hAudioThread(NULL),
      m_hasCapture(false),
      m_hasRender(false),
      m_isExclusiveActive(false),
      m_isRenderFloat(false),
      m_isCaptureFloat(false)
{
    InitializeCriticalSection(&m_lock);
    memset(m_errorMessage, 0, sizeof(m_errorMessage));

    for (int c = 0; c < NUM_INPUT_CHANNELS; c++) {
        m_inBuffers[c][0] = NULL;
        m_inBuffers[c][1] = NULL;
    }
    for (int c = 0; c < NUM_OUTPUT_CHANNELS; c++) {
        m_outBuffers[c][0] = NULL;
        m_outBuffers[c][1] = NULL;
    }

    loadConfig();
    AsioLog("CSMK37ProASIO instance created (buf=%ld, sr=%.0f, excl=%d)", m_bufferSize, m_sampleRate, m_exclusiveMode);
}

CSMK37ProASIO::~CSMK37ProASIO() {
    AsioLog("CSMK37ProASIO destructor called");
    stop();
    disposeBuffers();
    closeWASAPI();
    DeleteCriticalSection(&m_lock);
}

// ---------------------------------------------------------------- IUnknown
STDMETHODIMP CSMK37ProASIO::QueryInterface(REFIID riid, LPVOID* ppvObj) {
    if (!ppvObj) return E_POINTER;
    *ppvObj = NULL;

    bool match = (IsEqualIID(riid, IID_IUnknown) ||
                  IsEqualIID(riid, IID_IASIO) ||
                  IsEqualIID(riid, CLSID_SMK37Pro_ASIO));

    AsioLog("CSMK37ProASIO::QueryInterface: matched=%d (IUnknown=%d, IASIO=%d, CLSID=%d)",
            match,
            IsEqualIID(riid, IID_IUnknown),
            IsEqualIID(riid, IID_IASIO),
            IsEqualIID(riid, CLSID_SMK37Pro_ASIO));

    if (match) {
        *ppvObj = static_cast<IASIO*>(this);
        AddRef();
        return S_OK;
    }

    AsioLog("CSMK37ProASIO::QueryInterface -> E_NOINTERFACE ({%08lX-%04hX-%04hX-%02hhX%02hhX-%02hhX%02hhX%02hhX%02hhX%02hhX%02hhX})",
            riid.Data1, riid.Data2, riid.Data3,
            riid.Data4[0], riid.Data4[1], riid.Data4[2], riid.Data4[3],
            riid.Data4[4], riid.Data4[5], riid.Data4[6], riid.Data4[7]);
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) CSMK37ProASIO::AddRef() {
    return InterlockedIncrement(&m_refCount);
}

STDMETHODIMP_(ULONG) CSMK37ProASIO::Release() {
    ULONG count = InterlockedDecrement(&m_refCount);
    if (count == 0) {
        delete this;
    }
    return count;
}

// ---------------------------------------------------------------- IASIO
ASIOBool CSMK37ProASIO::init(void *sysHandle) {
    AsioLog("CSMK37ProASIO::init(sysHandle=%p)", sysHandle);
    EnterCriticalSection(&m_lock);
    m_hParentWnd = (HWND)sysHandle;

    if (m_initialized) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::init -> already initialized");
        return ASIOTrue;
    }

    HRESULT hr = CoInitialize(NULL);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
        AsioLog("CSMK37ProASIO::init -> CoInitialize warning: 0x%08X", (unsigned int)hr);
    }

    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL, CLSCTX_ALL,
                          __uuidof(IMMDeviceEnumerator), (void**)&m_pEnumerator);
    if (FAILED(hr)) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "Failed to initialize MMDeviceEnumerator (0x%08X)", (unsigned int)hr);
        AsioLog("CSMK37ProASIO::init -> ERROR: CoCreateInstance MMDeviceEnumerator failed: 0x%08X", (unsigned int)hr);
        LeaveCriticalSection(&m_lock);
        return ASIOFalse;
    }

    m_initialized = true;
    LeaveCriticalSection(&m_lock);
    AsioLog("CSMK37ProASIO::init -> SUCCESS");
    return ASIOTrue;
}

void CSMK37ProASIO::getDriverName(char *name) {
    if (name) {
        strncpy(name, DRIVER_NAME, 31);
        name[31] = '\0';
    }
    AsioLog("CSMK37ProASIO::getDriverName -> %s", name ? name : "");
}

long CSMK37ProASIO::getDriverVersion() {
    AsioLog("CSMK37ProASIO::getDriverVersion -> %ld", DRIVER_VERSION);
    return DRIVER_VERSION;
}

void CSMK37ProASIO::getErrorMessage(char *string) {
    if (string) {
        strncpy(string, m_errorMessage, 127);
        string[127] = '\0';
    }
    AsioLog("CSMK37ProASIO::getErrorMessage -> %s", string ? string : "");
}

ASIOError CSMK37ProASIO::start() {
    AsioLog("CSMK37ProASIO::start() requested");
    EnterCriticalSection(&m_lock);
    if (!m_initialized) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::start -> ASE_NotPresent");
        return ASE_NotPresent;
    }
    if (m_running) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::start -> already running");
        return ASE_OK;
    }

    if (!initWASAPI()) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::start -> initWASAPI failed!");
        return ASE_HWMalfunction;
    }

    m_ringBufferOut.reset();
    m_ringBufferIn.reset();

    // Pre-roll: write 2 buffers of silence to ring buffer out as safety cushion
    m_ringBufferOut.writeSilence(m_bufferSize * 2);

    m_hStopEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    m_running = true;
    m_hAudioThread = CreateThread(NULL, 0, AudioThreadEntry, this, 0, NULL);
    if (!m_hAudioThread) {
        m_running = false;
        closeWASAPI();
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::start -> CreateThread failed!");
        return ASE_HWMalfunction;
    }

    SetThreadPriority(m_hAudioThread, THREAD_PRIORITY_TIME_CRITICAL);

    LeaveCriticalSection(&m_lock);
    AsioLog("CSMK37ProASIO::start -> STARTED successfully (buf=%ld, preroll=%ld, exclusive=%d)",
            m_bufferSize, m_bufferSize * 2, m_isExclusiveActive);
    return ASE_OK;
}

ASIOError CSMK37ProASIO::stop() {
    AsioLog("CSMK37ProASIO::stop() requested");
    EnterCriticalSection(&m_lock);
    if (!m_running) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::stop -> not running");
        return ASE_OK;
    }

    m_running = false;
    if (m_hStopEvent) {
        SetEvent(m_hStopEvent);
    }

    HANDLE hThread = m_hAudioThread;
    m_hAudioThread = NULL;
    LeaveCriticalSection(&m_lock);

    // Wait cleanly for audio thread to exit without holding m_lock (prevents deadlocks with DAW)
    if (hThread) {
        DWORD waitRes = WaitForSingleObject(hThread, 1500);
        if (waitRes == WAIT_TIMEOUT) {
            AsioLog("CSMK37ProASIO::stop -> Audio thread timeout, terminating thread safely");
            TerminateThread(hThread, 0);
        }
        CloseHandle(hThread);
    }

    EnterCriticalSection(&m_lock);
    if (m_hStopEvent) {
        CloseHandle(m_hStopEvent);
        m_hStopEvent = NULL;
    }

    closeWASAPI();
    m_ringBufferOut.reset();
    m_ringBufferIn.reset();
    LeaveCriticalSection(&m_lock);
    AsioLog("CSMK37ProASIO::stop -> STOPPED");
    return ASE_OK;
}

ASIOError CSMK37ProASIO::getChannels(long *numInputChannels, long *numOutputChannels) {
    if (numInputChannels)  *numInputChannels  = NUM_INPUT_CHANNELS;
    if (numOutputChannels) *numOutputChannels = NUM_OUTPUT_CHANNELS;
    AsioLog("CSMK37ProASIO::getChannels -> in=%ld, out=%ld",
            numInputChannels ? *numInputChannels : 0,
            numOutputChannels ? *numOutputChannels : 0);
    return ASE_OK;
}

ASIOError CSMK37ProASIO::getLatencies(long *inputLatency, long *outputLatency) {
    if (inputLatency)  *inputLatency  = m_bufferSize;
    if (outputLatency) *outputLatency = m_isExclusiveActive ? m_bufferSize : (m_bufferSize * 2);
    AsioLog("CSMK37ProASIO::getLatencies -> in=%ld, out=%ld (exclusive=%d)",
            inputLatency ? *inputLatency : 0,
            outputLatency ? *outputLatency : 0,
            m_isExclusiveActive);
    return ASE_OK;
}

ASIOError CSMK37ProASIO::getBufferSize(long *minSize, long *maxSize, long *preferredSize, long *granularity) {
    if (minSize)       *minSize       = MIN_BUFFER_SIZE;
    if (maxSize)       *maxSize       = MAX_BUFFER_SIZE;
    if (preferredSize) *preferredSize = m_pendingBufferSize ? m_pendingBufferSize : m_bufferSize;
    if (granularity)   *granularity   = -1; // -1 = power-of-two (32, 64, 128, 256, 512, 1024, 2048)
    AsioLog("CSMK37ProASIO::getBufferSize -> min=%ld, max=%ld, pref=%ld, gran=-1",
            MIN_BUFFER_SIZE, MAX_BUFFER_SIZE, preferredSize ? *preferredSize : 0);
    return ASE_OK;
}

ASIOError CSMK37ProASIO::canSampleRate(ASIOSampleRate sampleRate) {
    ASIOError err = (sampleRate == 44100.0) ? ASE_OK : ASE_NoClock;
    if (sampleRate == 48000.0) err = ASE_OK;
    AsioLog("CSMK37ProASIO::canSampleRate(%.0f) -> %s", sampleRate, err == ASE_OK ? "OK" : "NoClock");
    return err;
}

ASIOError CSMK37ProASIO::getSampleRate(ASIOSampleRate *sampleRate) {
    if (sampleRate) *sampleRate = m_sampleRate;
    return ASE_OK;
}

ASIOError CSMK37ProASIO::setSampleRate(ASIOSampleRate sampleRate) {
    AsioLog("CSMK37ProASIO::setSampleRate(%.0f)", sampleRate);
    if (canSampleRate(sampleRate) != ASE_OK) {
        return ASE_NoClock;
    }
    m_sampleRate = sampleRate;
    if (m_callbacks && m_callbacks->sampleRateDidChange) {
        m_callbacks->sampleRateDidChange(sampleRate);
    }
    return ASE_OK;
}

ASIOError CSMK37ProASIO::getClockSources(ASIOClockSource *clocks, long *numSources) {
    if (numSources) *numSources = 1;
    if (clocks) {
        clocks[0].index = 0;
        clocks[0].associatedChannel = -1;
        clocks[0].associatedGroup = -1;
        clocks[0].isCurrentSource = ASIOTrue;
        strncpy(clocks[0].name, "Internal Clock", 31);
    }
    return ASE_OK;
}

ASIOError CSMK37ProASIO::setClockSource(long reference) {
    if (reference == 0) return ASE_OK;
    return ASE_NotPresent;
}

ASIOError CSMK37ProASIO::getSamplePosition(ASIOSamples *sPos, ASIOTimeStamp *tStamp) {
    if (sPos) {
        sPos->hi = (unsigned long)(m_samplePosition >> 32);
        sPos->lo = (unsigned long)(m_samplePosition & 0xFFFFFFFF);
    }
    if (tStamp) {
        LARGE_INTEGER qpcFreq;
        QueryPerformanceFrequency(&qpcFreq);
        int64_t nanos = GetWallClockNanoseconds(qpcFreq);
        tStamp->hi = (unsigned long)(nanos >> 32);
        tStamp->lo = (unsigned long)(nanos & 0xFFFFFFFF);
    }
    return ASE_OK;
}

ASIOError CSMK37ProASIO::getChannelInfo(ASIOChannelInfo *info) {
    if (!info) return ASE_InvalidParameter;

    if (info->isInput) {
        if (info->channel < 0 || info->channel >= NUM_INPUT_CHANNELS) return ASE_InvalidParameter;
        info->isActive = ASIOTrue;
        info->channelGroup = 0;
        info->type = ASIOSTInt32LSB;
        if (info->channel == 0) strncpy(info->name, "SMK-37 In L (DX7)", 31);
        else strncpy(info->name, "SMK-37 In R (DX7)", 31);
    } else {
        if (info->channel < 0 || info->channel >= NUM_OUTPUT_CHANNELS) return ASE_InvalidParameter;
        info->isActive = ASIOTrue;
        info->channelGroup = 0;
        info->type = ASIOSTInt32LSB;
        if (info->channel == 0) strncpy(info->name, "SMK-37 Out L", 31);
        else strncpy(info->name, "SMK-37 Out R", 31);
    }
    return ASE_OK;
}

ASIOError CSMK37ProASIO::createBuffers(ASIOBufferInfo *bufferInfos, long numChannels, long bufferSize, ASIOCallbacks *callbacks) {
    AsioLog("CSMK37ProASIO::createBuffers(numChannels=%ld, bufferSize=%ld, callbacks=%p)", numChannels, bufferSize, callbacks);
    EnterCriticalSection(&m_lock);
    if (!bufferInfos || !callbacks) {
        LeaveCriticalSection(&m_lock);
        AsioLog("CSMK37ProASIO::createBuffers -> ASE_InvalidParameter");
        return ASE_InvalidParameter;
    }

    if (bufferSize < MIN_BUFFER_SIZE) bufferSize = MIN_BUFFER_SIZE;
    if (bufferSize > MAX_BUFFER_SIZE) bufferSize = MAX_BUFFER_SIZE;

    disposeBuffers();

    m_bufferSize = bufferSize;
    m_pendingBufferSize = bufferSize;
    m_allocatedBufferSize = bufferSize;
    m_numChannels = numChannels;
    m_bufferInfos = bufferInfos;
    m_callbacks = callbacks;
    m_doubleBufferIndex = 0;
    m_samplePosition = 0;

    // Allocate 32-bit sample buffers for inputs and outputs
    for (int c = 0; c < NUM_INPUT_CHANNELS; c++) {
        m_inBuffers[c][0] = new int32_t[m_allocatedBufferSize]();
        m_inBuffers[c][1] = new int32_t[m_allocatedBufferSize]();
    }
    for (int c = 0; c < NUM_OUTPUT_CHANNELS; c++) {
        m_outBuffers[c][0] = new int32_t[m_allocatedBufferSize]();
        m_outBuffers[c][1] = new int32_t[m_allocatedBufferSize]();
    }

    // Populate DAW buffer pointers
    for (int i = 0; i < numChannels; i++) {
        long ch = bufferInfos[i].channelNum;
        if (bufferInfos[i].isInput) {
            if (ch >= 0 && ch < NUM_INPUT_CHANNELS) {
                bufferInfos[i].buffers[0] = m_inBuffers[ch][0];
                bufferInfos[i].buffers[1] = m_inBuffers[ch][1];
            }
        } else {
            if (ch >= 0 && ch < NUM_OUTPUT_CHANNELS) {
                bufferInfos[i].buffers[0] = m_outBuffers[ch][0];
                bufferInfos[i].buffers[1] = m_outBuffers[ch][1];
            }
        }
    }

    LeaveCriticalSection(&m_lock);
    AsioLog("CSMK37ProASIO::createBuffers -> SUCCESS");
    return ASE_OK;
}

ASIOError CSMK37ProASIO::disposeBuffers() {
    AsioLog("CSMK37ProASIO::disposeBuffers() called");
    EnterCriticalSection(&m_lock);
    if (m_running) {
        LeaveCriticalSection(&m_lock);
        stop();
        EnterCriticalSection(&m_lock);
    }
    for (int c = 0; c < NUM_INPUT_CHANNELS; c++) {
        delete[] m_inBuffers[c][0]; m_inBuffers[c][0] = NULL;
        delete[] m_inBuffers[c][1]; m_inBuffers[c][1] = NULL;
    }
    for (int c = 0; c < NUM_OUTPUT_CHANNELS; c++) {
        delete[] m_outBuffers[c][0]; m_outBuffers[c][0] = NULL;
        delete[] m_outBuffers[c][1]; m_outBuffers[c][1] = NULL;
    }
    m_bufferInfos = NULL;
    m_callbacks = NULL;
    m_allocatedBufferSize = 0;
    LeaveCriticalSection(&m_lock);
    return ASE_OK;
}

void CSMK37ProASIO::scheduleDeferredReset() {
    // Foreign-thread asioMessage calls cause immediate CTDs or thread deadlocks in DAW hosts.
    // Safe no-op: host queries getBufferSize upon dialog dismiss and manages reset cleanly.
}

// ---------------------------------------------------------------- Control Panel GUI
static LRESULT CALLBACK ControlPanelWndProc(HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
    CSMK37ProASIO* pDrv = (CSMK37ProASIO*)GetWindowLongPtrW(hWnd, GWLP_USERDATA);

    switch (uMsg) {
        case WM_CREATE: {
            CREATESTRUCTW* pCS = (CREATESTRUCTW*)lParam;
            pDrv = (CSMK37ProASIO*)pCS->lpCreateParams;
            SetWindowLongPtrW(hWnd, GWLP_USERDATA, (LONG_PTR)pDrv);
            return 0;
        }
        case WM_COMMAND: {
            int wmId = LOWORD(wParam);
            if (wmId == IDOK && pDrv) {
                HWND hCombo = GetDlgItem(hWnd, 102);
                HWND hChk = GetDlgItem(hWnd, 103);
                int sel = (int)SendMessageW(hCombo, CB_GETCURSEL, 0, 0);
                bool changed = false;
                if (sel != CB_ERR) {
                    long newBuf = (long)SendMessageW(hCombo, CB_GETITEMDATA, sel, 0);
                    if (newBuf != pDrv->m_bufferSize || newBuf != pDrv->m_pendingBufferSize) {
                        pDrv->m_pendingBufferSize = newBuf;
                        pDrv->m_bufferSize = newBuf;
                        changed = true;
                    }
                }
                bool newEx = (SendMessageW(hChk, BM_GETCHECK, 0, 0) == BST_CHECKED);
                if (newEx != pDrv->m_exclusiveMode) {
                    pDrv->m_exclusiveMode = newEx;
                    changed = true;
                }
                if (changed) {
                    pDrv->saveConfig();
                    AsioLog("ControlPanel: Settings updated (buf=%ld, excl=%d)", pDrv->m_bufferSize, pDrv->m_exclusiveMode);
                }
                DestroyWindow(hWnd);
                return 0;
            } else if (wmId == IDCANCEL) {
                DestroyWindow(hWnd);
                return 0;
            }
            break;
        }
        case WM_CLOSE: {
            DestroyWindow(hWnd);
            return 0;
        }
        case WM_DESTROY: {
            PostQuitMessage(0);
            return 0;
        }
    }
    return DefWindowProcW(hWnd, uMsg, wParam, lParam);
}

ASIOError CSMK37ProASIO::controlPanel() {
    HWND hOwner = m_hParentWnd ? m_hParentWnd : GetActiveWindow();

    static bool classRegistered = false;
    if (!classRegistered) {
        WNDCLASSEXW wc = { sizeof(wc) };
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = ControlPanelWndProc;
        wc.hInstance = g_hInstance;
        wc.hCursor = LoadCursor(NULL, IDC_ARROW);
        wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
        wc.lpszClassName = L"SMK37Pro_ASIO_ControlPanel";
        RegisterClassExW(&wc);
        classRegistered = true;
    }

    HWND hWnd = CreateWindowExW(
        WS_EX_DLGMODALFRAME | WS_EX_TOPMOST,
        L"SMK37Pro_ASIO_ControlPanel", L"M-VAVE SMK-37 Pro ASIO Settings",
        WS_POPUP | WS_CAPTION | WS_SYSMENU,
        (GetSystemMetrics(SM_CXSCREEN) - 400) / 2,
        (GetSystemMetrics(SM_CYSCREEN) - 230) / 2,
        400, 230, hOwner, NULL, g_hInstance, this
    );

    if (hWnd) {
        HFONT hFont = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

        CreateWindowW(L"STATIC", L"Device Endpoint:", WS_VISIBLE | WS_CHILD,
                      20, 20, 120, 20, hWnd, NULL, g_hInstance, NULL);
        HWND hDevStatic = CreateWindowW(L"STATIC", m_detectedDevName.c_str(), WS_VISIBLE | WS_CHILD | SS_PATHELLIPSIS,
                                        140, 20, 220, 20, hWnd, (HMENU)101, g_hInstance, NULL);

        CreateWindowW(L"STATIC", L"ASIO Buffer Size:", WS_VISIBLE | WS_CHILD,
                      20, 55, 120, 20, hWnd, NULL, g_hInstance, NULL);
        HWND hCombo = CreateWindowW(L"COMBOBOX", NULL, WS_VISIBLE | WS_CHILD | CBS_DROPDOWNLIST | WS_VSCROLL,
                                    140, 50, 220, 180, hWnd, (HMENU)102, g_hInstance, NULL);

        const int buffer_sizes[] = {32, 64, 128, 256, 512, 1024, 2048};
        for (int sz : buffer_sizes) {
            wchar_t itemText[64];
            double latMs = (sz / m_sampleRate) * 1000.0;
            swprintf(itemText, 64, L"%d samples (%.2f ms)", sz, latMs);
            int idx = (int)SendMessageW(hCombo, CB_ADDSTRING, 0, (LPARAM)itemText);
            SendMessageW(hCombo, CB_SETITEMDATA, idx, sz);
            long currentSelected = m_pendingBufferSize ? m_pendingBufferSize : m_bufferSize;
            if (sz == currentSelected) {
                SendMessageW(hCombo, CB_SETCURSEL, idx, 0);
            }
        }

        HWND hChk = CreateWindowW(L"BUTTON", L"WASAPI Exclusive Mode (Ultra-Low Latency)",
                                  WS_VISIBLE | WS_CHILD | BS_AUTOCHECKBOX,
                                  20, 95, 340, 20, hWnd, (HMENU)103, g_hInstance, NULL);
        SendMessageW(hChk, BM_SETCHECK, m_exclusiveMode ? BST_CHECKED : BST_UNCHECKED, 0);

        HWND hTip = CreateWindowW(L"STATIC", L"* Tip: In Ableton, buffer size can also be set in Preferences.",
                                  WS_VISIBLE | WS_CHILD, 20, 122, 360, 18, hWnd, NULL, g_hInstance, NULL);

        HWND hBtnOk = CreateWindowW(L"BUTTON", L"Apply & Close", WS_VISIBLE | WS_CHILD | BS_DEFPUSHBUTTON,
                                    250, 150, 110, 30, hWnd, (HMENU)IDOK, g_hInstance, NULL);
        HWND hBtnCancel = CreateWindowW(L"BUTTON", L"Cancel", WS_VISIBLE | WS_CHILD,
                                        130, 150, 100, 30, hWnd, (HMENU)IDCANCEL, g_hInstance, NULL);

        SendMessageW(hDevStatic, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessageW(hCombo, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessageW(hChk, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessageW(hTip, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessageW(hBtnOk, WM_SETFONT, (WPARAM)hFont, TRUE);
        SendMessageW(hBtnCancel, WM_SETFONT, (WPARAM)hFont, TRUE);

        ShowWindow(hWnd, SW_SHOW);
        UpdateWindow(hWnd);

        if (hOwner) EnableWindow(hOwner, FALSE);

        MSG msg;
        while (GetMessageW(&msg, NULL, 0, 0)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }

        if (hOwner) {
            EnableWindow(hOwner, TRUE);
            SetForegroundWindow(hOwner);
        }
    }

    return ASE_OK;
}

ASIOError CSMK37ProASIO::future(long selector, void *opt) {
    AsioLog("CSMK37ProASIO::future(selector=%ld)", selector);
    switch (selector) {
        case 10: // kAsioCanTimeInfo
            return ASE_SUCCESS;
        default:
            return ASE_NotPresent;
    }
}

ASIOError CSMK37ProASIO::outputReady() {
    return ASE_OK;
}

// ---------------------------------------------------------------- WASAPI Engine
static bool ContainsSubstringCI(const std::wstring& str, const std::wstring& sub) {
    if (sub.empty() || str.length() < sub.length()) return false;
    std::wstring lowerStr = str;
    std::wstring lowerSub = sub;
    for (auto& c : lowerStr) c = (wchar_t)towlower(c);
    for (auto& c : lowerSub) c = (wchar_t)towlower(c);
    return lowerStr.find(lowerSub) != std::wstring::npos;
}

static IMMDevice* FindSpecificAudioDevice(IMMDeviceEnumerator* pEnum, EDataFlow dataFlow, std::wstring& outName) {
    if (!pEnum) return NULL;

    IMMDeviceCollection* pCol = NULL;
    HRESULT hr = pEnum->EnumAudioEndpoints(dataFlow, DEVICE_STATE_ACTIVE, &pCol);
    if (FAILED(hr) || !pCol) return NULL;

    UINT count = 0;
    pCol->GetCount(&count);

    const wchar_t* primaryKeywords[] = { L"SMK-37", L"SMK37", L"SMK", L"M-VAVE", L"Sinco" };
    const wchar_t* secondaryKeywords[] = { L"Pro Audio", L"Audio USB", L"USB Audio", L"Dispositivo de audio USB" };

    // Pass 1: Match primary keywords (SMK / M-VAVE specific)
    for (UINT i = 0; i < count; i++) {
        IMMDevice* pDev = NULL;
        if (SUCCEEDED(pCol->Item(i, &pDev)) && pDev) {
            IPropertyStore* pProps = NULL;
            if (SUCCEEDED(pDev->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
                PROPVARIANT varName;
                PropVariantInit(&varName);
                if (SUCCEEDED(pProps->GetValue(PKEY_Device_FriendlyName, &varName)) && varName.pwszVal) {
                    std::wstring devName = varName.pwszVal;
                    for (const auto& kw : primaryKeywords) {
                        if (ContainsSubstringCI(devName, kw)) {
                            outName = devName;
                            pDev->AddRef();
                            PropVariantClear(&varName);
                            pProps->Release();
                            pCol->Release();
                            AsioLog("FindSpecificAudioDevice: Primary match [%S]", outName.c_str());
                            return pDev;
                        }
                    }
                }
                PropVariantClear(&varName);
                pProps->Release();
            }
            pDev->Release();
        }
    }

    // Pass 2: Match secondary keywords (Generic USB Audio endpoints)
    for (UINT i = 0; i < count; i++) {
        IMMDevice* pDev = NULL;
        if (SUCCEEDED(pCol->Item(i, &pDev)) && pDev) {
            IPropertyStore* pProps = NULL;
            if (SUCCEEDED(pDev->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
                PROPVARIANT varName;
                PropVariantInit(&varName);
                if (SUCCEEDED(pProps->GetValue(PKEY_Device_FriendlyName, &varName)) && varName.pwszVal) {
                    std::wstring devName = varName.pwszVal;
                    for (const auto& kw : secondaryKeywords) {
                        if (ContainsSubstringCI(devName, kw)) {
                            outName = devName;
                            pDev->AddRef();
                            PropVariantClear(&varName);
                            pProps->Release();
                            pCol->Release();
                            AsioLog("FindSpecificAudioDevice: Secondary match [%S]", outName.c_str());
                            return pDev;
                        }
                    }
                }
                PropVariantClear(&varName);
                pProps->Release();
            }
            pDev->Release();
        }
    }

    pCol->Release();

    // Fallback: Default Audio Endpoint
    IMMDevice* pDef = NULL;
    if (SUCCEEDED(pEnum->GetDefaultAudioEndpoint(dataFlow, eMultimedia, &pDef)) && pDef) {
        IPropertyStore* pProps = NULL;
        if (SUCCEEDED(pDef->OpenPropertyStore(STGM_READ, &pProps)) && pProps) {
            PROPVARIANT varName;
            PropVariantInit(&varName);
            if (SUCCEEDED(pProps->GetValue(PKEY_Device_FriendlyName, &varName)) && varName.pwszVal) {
                outName = varName.pwszVal;
            }
            PropVariantClear(&varName);
            pProps->Release();
        }
        AsioLog("FindSpecificAudioDevice: Fallback to default endpoint [%S]", outName.c_str());
        return pDef;
    }

    return NULL;
}

bool CSMK37ProASIO::initWASAPI() {
    closeWASAPI();

    if (!m_pEnumerator) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "IMMDeviceEnumerator is null");
        return false;
    }

    // Find SMK-37 Pro Render (Out) & Capture (In)
    std::wstring renderName, captureName;
    m_pRenderDevice  = FindSpecificAudioDevice(m_pEnumerator, eRender, renderName);
    m_pCaptureDevice = FindSpecificAudioDevice(m_pEnumerator, eCapture, captureName);

    AsioLog("initWASAPI: Selected Render='%S', Capture='%S'", renderName.c_str(), captureName.c_str());

    if (m_pRenderDevice) {
        m_detectedDevName = renderName;
        m_deviceFound = (ContainsSubstringCI(renderName, L"SMK") ||
                         ContainsSubstringCI(renderName, L"M-VAVE") ||
                         ContainsSubstringCI(renderName, L"Sinco"));
    } else {
        m_detectedDevName = L"No Audio Device Found";
        snprintf(m_errorMessage, sizeof(m_errorMessage), "No audio output device found on system");
        AsioLog("initWASAPI: ERROR - No audio output device found!");
        return false;
    }

    HRESULT hr = S_OK;

    // 1. Setup Render Client (Stereo Out)
    hr = m_pRenderDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&m_pRenderClient);
    if (FAILED(hr) || !m_pRenderClient) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "Activate Render IAudioClient failed: 0x%08X", (unsigned int)hr);
        AsioLog("initWASAPI: ERROR - Activate Render failed: 0x%08X", (unsigned int)hr);
        return false;
    }

    m_isExclusiveActive = false;
    m_isRenderFloat = false;
    m_isCaptureFloat = false;

    REFERENCE_TIME hnsRequested = (REFERENCE_TIME)(((double)m_bufferSize * 10000000.0 / m_sampleRate) + 0.5);
    DWORD streamFlags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK;

    // Try Exclusive Mode if requested
    if (m_exclusiveMode) {
        REFERENCE_TIME defPeriod = 0, minPeriod = 0;
        m_pRenderClient->GetDevicePeriod(&defPeriod, &minPeriod);
        REFERENCE_TIME hnsExclusive = hnsRequested;
        if (minPeriod > 0 && hnsExclusive < minPeriod) {
            hnsExclusive = minPeriod;
        }

        // Format Candidates for Exclusive Mode
        // Candidate 1: 32-bit IEEE Float (Native SMK-37 mix format)
        WAVEFORMATEXTENSIBLE wfeFloat;
        ZeroMemory(&wfeFloat, sizeof(wfeFloat));
        wfeFloat.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
        wfeFloat.Format.nChannels = 2;
        wfeFloat.Format.nSamplesPerSec = (DWORD)m_sampleRate;
        wfeFloat.Format.wBitsPerSample = 32;
        wfeFloat.Format.nBlockAlign = 8;
        wfeFloat.Format.nAvgBytesPerSec = (DWORD)m_sampleRate * 8;
        wfeFloat.Format.cbSize = 22;
        wfeFloat.Samples.wValidBitsPerSample = 32;
        wfeFloat.dwChannelMask = KSAUDIO_SPEAKER_STEREO;
        wfeFloat.SubFormat = GUID_SUBTYPE_IEEE_FLOAT;

        // Candidate 2: 24-bit in 32-bit container PCM
        WAVEFORMATEXTENSIBLE wfePcm24;
        ZeroMemory(&wfePcm24, sizeof(wfePcm24));
        wfePcm24.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
        wfePcm24.Format.nChannels = 2;
        wfePcm24.Format.nSamplesPerSec = (DWORD)m_sampleRate;
        wfePcm24.Format.wBitsPerSample = 32;
        wfePcm24.Format.nBlockAlign = 8;
        wfePcm24.Format.nAvgBytesPerSec = (DWORD)m_sampleRate * 8;
        wfePcm24.Format.cbSize = 22;
        wfePcm24.Samples.wValidBitsPerSample = 24;
        wfePcm24.dwChannelMask = KSAUDIO_SPEAKER_STEREO;
        wfePcm24.SubFormat = GUID_SUBTYPE_PCM;

        // Candidate 3: 16-bit Standard PCM
        WAVEFORMATEXTENSIBLE wfePcm16;
        ZeroMemory(&wfePcm16, sizeof(wfePcm16));
        wfePcm16.Format.wFormatTag = WAVE_FORMAT_PCM;
        wfePcm16.Format.nChannels = 2;
        wfePcm16.Format.nSamplesPerSec = (DWORD)m_sampleRate;
        wfePcm16.Format.wBitsPerSample = 16;
        wfePcm16.Format.nBlockAlign = 4;
        wfePcm16.Format.nAvgBytesPerSec = (DWORD)m_sampleRate * 4;
        wfePcm16.Format.cbSize = 0;

        WAVEFORMATEXTENSIBLE* candidates[] = { &wfeFloat, &wfePcm24, &wfePcm16 };
        for (int c = 0; c < 3; c++) {
            if (!m_pRenderClient) {
                if (FAILED(m_pRenderDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&m_pRenderClient)) || !m_pRenderClient) {
                    break;
                }
            }
            memcpy(&m_renderFormat, candidates[c], sizeof(WAVEFORMATEXTENSIBLE));
            hr = m_pRenderClient->Initialize(AUDCLNT_SHAREMODE_EXCLUSIVE, streamFlags, hnsExclusive, hnsExclusive,
                                             (WAVEFORMATEX*)&m_renderFormat, NULL);

            if (hr == AUDCLNT_E_BUFFER_SIZE_NOT_ALIGNED) {
                UINT32 alignedFrames = 0;
                if (SUCCEEDED(m_pRenderClient->GetBufferSize(&alignedFrames)) && alignedFrames > 0) {
                    hnsExclusive = (REFERENCE_TIME)(((double)alignedFrames * 10000000.0 / m_sampleRate) + 0.5);
                    m_pRenderClient->Release();
                    m_pRenderClient = NULL;
                    if (SUCCEEDED(m_pRenderDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&m_pRenderClient)) && m_pRenderClient) {
                        hr = m_pRenderClient->Initialize(AUDCLNT_SHAREMODE_EXCLUSIVE, streamFlags, hnsExclusive, hnsExclusive,
                                                         (WAVEFORMATEX*)&m_renderFormat, NULL);
                    }
                }
            }

            if (SUCCEEDED(hr)) {
                m_isExclusiveActive = true;
                m_isRenderFloat = (c == 0);
                AsioLog("initWASAPI: Exclusive Mode initialized with Candidate %d (Float=%d)", c, m_isRenderFloat);
                break;
            } else {
                if (m_pRenderClient) {
                    m_pRenderClient->Release();
                    m_pRenderClient = NULL;
                }
            }
        }
    }

    // Graceful fallback to Shared Mode
    if (!m_isExclusiveActive) {
        if (m_pRenderClient) { m_pRenderClient->Release(); m_pRenderClient = NULL; }
        hr = m_pRenderDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&m_pRenderClient);
        if (FAILED(hr) || !m_pRenderClient) {
            snprintf(m_errorMessage, sizeof(m_errorMessage), "Re-activate Render IAudioClient failed: 0x%08X", (unsigned int)hr);
            AsioLog("initWASAPI: ERROR - Re-activate Render failed: 0x%08X", (unsigned int)hr);
            return false;
        }

        WAVEFORMATEX* pMix = NULL;
        hr = m_pRenderClient->GetMixFormat(&pMix);
        if (FAILED(hr) || !pMix) {
            snprintf(m_errorMessage, sizeof(m_errorMessage), "GetMixFormat failed: 0x%08X", (unsigned int)hr);
            AsioLog("initWASAPI: ERROR - GetMixFormat failed: 0x%08X", (unsigned int)hr);
            return false;
        }

        if (pMix->wFormatTag == WAVE_FORMAT_EXTENSIBLE && pMix->cbSize >= 22) {
            memcpy(&m_renderFormat, pMix, sizeof(WAVEFORMATEXTENSIBLE));
        } else {
            memset(&m_renderFormat, 0, sizeof(m_renderFormat));
            memcpy(&m_renderFormat.Format, pMix, sizeof(WAVEFORMATEX));
            m_renderFormat.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
            m_renderFormat.Format.cbSize = 22;
            m_renderFormat.Samples.wValidBitsPerSample = pMix->wBitsPerSample;
            m_renderFormat.dwChannelMask = (pMix->nChannels == 1) ? KSAUDIO_SPEAKER_MONO : KSAUDIO_SPEAKER_STEREO;
            m_renderFormat.SubFormat = (pMix->wBitsPerSample == 32 && (pMix->wFormatTag == 3)) ? GUID_SUBTYPE_IEEE_FLOAT : GUID_SUBTYPE_PCM;
        }

        m_isRenderFloat = IsEqualGUID(m_renderFormat.SubFormat, GUID_SUBTYPE_IEEE_FLOAT) || (pMix->wFormatTag == 3);
        CoTaskMemFree(pMix);

        hr = m_pRenderClient->Initialize(AUDCLNT_SHAREMODE_SHARED, streamFlags, hnsRequested, 0,
                                         (WAVEFORMATEX*)&m_renderFormat, NULL);
        if (FAILED(hr)) {
            snprintf(m_errorMessage, sizeof(m_errorMessage), "Initialize Shared failed: 0x%08X", (unsigned int)hr);
            AsioLog("initWASAPI: ERROR - Initialize Shared failed: 0x%08X", (unsigned int)hr);
            return false;
        }
        m_isExclusiveActive = false;
    }

    AsioLog("initWASAPI: Render Client Ready (Mode=%s, Bits=%u, Rate=%u, Float=%d)",
            m_isExclusiveActive ? "EXCLUSIVE" : "SHARED",
            m_renderFormat.Format.wBitsPerSample,
            m_renderFormat.Format.nSamplesPerSec,
            m_isRenderFloat);

    m_hRenderEvent = CreateEvent(NULL, FALSE, FALSE, NULL);
    hr = m_pRenderClient->SetEventHandle(m_hRenderEvent);
    if (FAILED(hr)) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "SetEventHandle failed: 0x%08X", (unsigned int)hr);
        AsioLog("initWASAPI: ERROR - SetEventHandle failed: 0x%08X", (unsigned int)hr);
        return false;
    }

    hr = m_pRenderClient->GetService(__uuidof(IAudioRenderClient), (void**)&m_pRenderService);
    if (FAILED(hr) || !m_pRenderService) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "GetService IAudioRenderClient failed: 0x%08X", (unsigned int)hr);
        AsioLog("initWASAPI: ERROR - GetService IAudioRenderClient failed: 0x%08X", (unsigned int)hr);
        return false;
    }

    // MANDATORY PRE-ROLL: Priming buffer with silence is strictly required by WASAPI before Start()
    UINT32 totalFrames = 0;
    if (SUCCEEDED(m_pRenderClient->GetBufferSize(&totalFrames)) && totalFrames > 0) {
        BYTE* pData = NULL;
        if (SUCCEEDED(m_pRenderService->GetBuffer(totalFrames, &pData)) && pData) {
            memset(pData, 0, totalFrames * m_renderFormat.Format.nBlockAlign);
            m_pRenderService->ReleaseBuffer(totalFrames, 0);
        }
    }

    hr = m_pRenderClient->Start();
    if (FAILED(hr)) {
        snprintf(m_errorMessage, sizeof(m_errorMessage), "RenderClient Start failed: 0x%08X", (unsigned int)hr);
        AsioLog("initWASAPI: ERROR - RenderClient Start failed: 0x%08X", (unsigned int)hr);
        return false;
    }
    m_hasRender = true;

    // 2. Setup Capture Client (Stereo In) if device exists
    if (m_pCaptureDevice) {
        hr = m_pCaptureDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL, (void**)&m_pCaptureClient);
        if (SUCCEEDED(hr) && m_pCaptureClient) {
            WAVEFORMATEX* pCapMix = NULL;
            if (SUCCEEDED(m_pCaptureClient->GetMixFormat(&pCapMix)) && pCapMix) {
                if (pCapMix->wFormatTag == WAVE_FORMAT_EXTENSIBLE && pCapMix->cbSize >= 22) {
                    memcpy(&m_captureFormat, pCapMix, sizeof(WAVEFORMATEXTENSIBLE));
                } else {
                    memset(&m_captureFormat, 0, sizeof(m_captureFormat));
                    memcpy(&m_captureFormat.Format, pCapMix, sizeof(WAVEFORMATEX));
                    m_captureFormat.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
                    m_captureFormat.Format.cbSize = 22;
                    m_captureFormat.Samples.wValidBitsPerSample = pCapMix->wBitsPerSample;
                    m_captureFormat.dwChannelMask = (pCapMix->nChannels == 1) ? KSAUDIO_SPEAKER_MONO : KSAUDIO_SPEAKER_STEREO;
                    m_captureFormat.SubFormat = (pCapMix->wBitsPerSample == 32 && (pCapMix->wFormatTag == 3)) ? GUID_SUBTYPE_IEEE_FLOAT : GUID_SUBTYPE_PCM;
                }
                m_isCaptureFloat = IsEqualGUID(m_captureFormat.SubFormat, GUID_SUBTYPE_IEEE_FLOAT) || (pCapMix->wFormatTag == 3);
                CoTaskMemFree(pCapMix);

                // Use polling stream for capture to avoid needing unhandled event handles
                hr = m_pCaptureClient->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, hnsRequested, 0,
                                                  (WAVEFORMATEX*)&m_captureFormat, NULL);
                if (SUCCEEDED(hr)) {
                    hr = m_pCaptureClient->GetService(__uuidof(IAudioCaptureClient), (void**)&m_pCaptureService);
                    if (SUCCEEDED(hr) && m_pCaptureService) {
                        m_pCaptureClient->Start();
                        m_hasCapture = true;
                        AsioLog("initWASAPI: Capture Client Ready (SHARED, Float=%d)", m_isCaptureFloat);
                    }
                }
            }
        }
    }

    return true;
}

void CSMK37ProASIO::closeWASAPI() {
    AsioLog("closeWASAPI called");
    if (m_pRenderClient)  m_pRenderClient->Stop();
    if (m_pCaptureClient) m_pCaptureClient->Stop();

    if (m_pRenderService)  { m_pRenderService->Release(); m_pRenderService = NULL; }
    if (m_pCaptureService) { m_pCaptureService->Release(); m_pCaptureService = NULL; }
    if (m_pRenderClient)   { m_pRenderClient->Release(); m_pRenderClient = NULL; }
    if (m_pCaptureClient)  { m_pCaptureClient->Release(); m_pCaptureClient = NULL; }
    if (m_pRenderDevice)   { m_pRenderDevice->Release(); m_pRenderDevice = NULL; }
    if (m_pCaptureDevice)  { m_pCaptureDevice->Release(); m_pCaptureDevice = NULL; }

    if (m_hRenderEvent)  { CloseHandle(m_hRenderEvent); m_hRenderEvent = NULL; }
    if (m_hCaptureEvent) { CloseHandle(m_hCaptureEvent); m_hCaptureEvent = NULL; }

    m_hasRender = false;
    m_hasCapture = false;
}

DWORD WINAPI CSMK37ProASIO::AudioThreadEntry(LPVOID lpParam) {
    CSMK37ProASIO* pThis = (CSMK37ProASIO*)lpParam;
    pThis->audioThreadLoop();
    return 0;
}

void CSMK37ProASIO::audioThreadLoop() {
    AsioLog("audioThreadLoop started");
    DWORD taskIndex = 0;
    HANDLE hAvrt = AvSetMmThreadCharacteristicsW(L"Pro Audio", &taskIndex);

    HANDLE waitHandles[2] = { m_hStopEvent, m_hRenderEvent };

    LARGE_INTEGER qpcFreq;
    QueryPerformanceFrequency(&qpcFreq);

    while (m_running) {
        DWORD waitRes = WaitForMultipleObjects(2, waitHandles, FALSE, 50);
        if (waitRes == WAIT_OBJECT_0) {
            // Stop requested
            break;
        }
        if (!m_running) break;

        if (waitRes == WAIT_TIMEOUT) {
            continue;
        }

        if (waitRes == WAIT_OBJECT_0 + 1) {
            // Audio Render Event Fired
            if (!m_running) break;

            if (!m_callbacks || (!m_callbacks->bufferSwitch && !m_callbacks->bufferSwitchTimeInfo) ||
                !m_outBuffers[0][0] || !m_outBuffers[1][0] || m_allocatedBufferSize < m_bufferSize) {
                continue;
            }

            // 1. Drain Capture Audio into Ring Buffer In
            if (m_hasCapture && m_pCaptureService) {
                UINT32 packetLength = 0;
                while (m_running && SUCCEEDED(m_pCaptureService->GetNextPacketSize(&packetLength)) && packetLength > 0) {
                    BYTE* pCapData = NULL;
                    UINT32 numFrames = 0;
                    DWORD flags = 0;
                    if (SUCCEEDED(m_pCaptureService->GetBuffer(&pCapData, &numFrames, &flags, NULL, NULL))) {
                        float tempInL[512], tempInR[512];
                        UINT32 framesRemaining = numFrames;
                        UINT32 offset = 0;
                        while (framesRemaining > 0) {
                            UINT32 chunk = (framesRemaining > 512) ? 512 : framesRemaining;
                            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                                m_ringBufferIn.writeSilence(chunk);
                            } else if (m_isCaptureFloat) {
                                float* pSrc = (float*)pCapData + (offset * 2);
                                for (UINT32 i = 0; i < chunk; i++) {
                                    tempInL[i] = pSrc[i * 2 + 0];
                                    tempInR[i] = pSrc[i * 2 + 1];
                                }
                                m_ringBufferIn.write(tempInL, tempInR, chunk);
                            } else if (m_captureFormat.Format.wBitsPerSample == 32) {
                                int32_t* pSrc = (int32_t*)pCapData + (offset * 2);
                                for (UINT32 i = 0; i < chunk; i++) {
                                    tempInL[i] = (float)pSrc[i * 2 + 0] / 2147483648.0f;
                                    tempInR[i] = (float)pSrc[i * 2 + 1] / 2147483648.0f;
                                }
                                m_ringBufferIn.write(tempInL, tempInR, chunk);
                            } else if (m_captureFormat.Format.wBitsPerSample == 16) {
                                int16_t* pSrc = (int16_t*)pCapData + (offset * 2);
                                for (UINT32 i = 0; i < chunk; i++) {
                                    tempInL[i] = (float)pSrc[i * 2 + 0] / 32768.0f;
                                    tempInR[i] = (float)pSrc[i * 2 + 1] / 32768.0f;
                                }
                                m_ringBufferIn.write(tempInL, tempInR, chunk);
                            }
                            offset += chunk;
                            framesRemaining -= chunk;
                        }
                        m_pCaptureService->ReleaseBuffer(numFrames);
                    }
                }
            }

            // 2. Determine frames needed by WASAPI Render Client
            UINT32 framesNeeded = 0;
            UINT32 totalFrames = 0;
            m_pRenderClient->GetBufferSize(&totalFrames);

            if (m_isExclusiveActive) {
                framesNeeded = totalFrames;
            } else {
                UINT32 paddingFrames = 0;
                m_pRenderClient->GetCurrentPadding(&paddingFrames);
                if (totalFrames > paddingFrames) {
                    framesNeeded = totalFrames - paddingFrames;
                }
            }

            if (framesNeeded == 0) continue;

            // 3. Keep Ring Buffer filled to satisfy framesNeeded + cushion
            // Dynamically compute iterations so small buffer sizes produce enough audio,
            // while capping at 12 to prevent host starvation and priority inversion.
            size_t targetLevel = framesNeeded + (size_t)m_bufferSize;
            int maxIterations = (int)((framesNeeded + m_bufferSize - 1) / m_bufferSize) + 1;
            if (maxIterations < 2) maxIterations = 2;
            if (maxIterations > 12) maxIterations = 12;

            // Measure accurate system wall-clock time right before invoking DAW buffer switch
            int64_t currentSystemTimeNanos = GetWallClockNanoseconds(qpcFreq);

            while (m_running && m_ringBufferOut.availableRead() < targetLevel && maxIterations-- > 0) {
                if (!m_callbacks || !m_outBuffers[0][0] || !m_outBuffers[1][0] || m_allocatedBufferSize < m_bufferSize) {
                    break;
                }

                long curSize = m_bufferSize;
                if (curSize > MAX_BUFFER_SIZE) curSize = MAX_BUFFER_SIZE;

                // Read capture from m_ringBufferIn into current double-buffer input
                float capL[MAX_BUFFER_SIZE], capR[MAX_BUFFER_SIZE];
                m_ringBufferIn.read(capL, capR, curSize);
                for (long i = 0; i < curSize; i++) {
                    m_inBuffers[0][m_doubleBufferIndex][i] = (int32_t)(capL[i] * 2147483647.0f);
                    m_inBuffers[1][m_doubleBufferIndex][i] = (int32_t)(capR[i] * 2147483647.0f);
                }

                // Construct accurate linear nanosecond ASIOTime with real wall-clock systemTime
                ASIOTime timeInfo;
                memset(&timeInfo, 0, sizeof(timeInfo));
                timeInfo.timeInfo.speed = 1.0;
                timeInfo.timeInfo.sampleRate = m_sampleRate;
                timeInfo.timeInfo.flags = 7; // kSystemTimeValid (1) | kSamplePositionValid (2) | kSampleRateValid (4)
                timeInfo.timeInfo.samplePosition.hi = (unsigned long)(m_samplePosition >> 32);
                timeInfo.timeInfo.samplePosition.lo = (unsigned long)(m_samplePosition & 0xFFFFFFFF);
                timeInfo.timeInfo.systemTime.hi = (unsigned long)(currentSystemTimeNanos >> 32);
                timeInfo.timeInfo.systemTime.lo = (unsigned long)(currentSystemTimeNanos & 0xFFFFFFFF);

                long activeBufIdx = m_doubleBufferIndex;
                m_doubleBufferIndex ^= 1;
                m_samplePosition += curSize;
                currentSystemTimeNanos += ((int64_t)curSize * 1000000000LL) / (int64_t)m_sampleRate;

                // Call DAW buffer callback safely
                if (m_callbacks->bufferSwitchTimeInfo) {
                    m_callbacks->bufferSwitchTimeInfo(&timeInfo, activeBufIdx, ASIOFalse);
                } else if (m_callbacks->bufferSwitch) {
                    m_callbacks->bufferSwitch(activeBufIdx, ASIOFalse);
                }

                if (!m_running) break;

                // Convert rendered int32 LSB samples to float and write to m_ringBufferOut
                float outL[MAX_BUFFER_SIZE], outR[MAX_BUFFER_SIZE];
                for (long i = 0; i < curSize; i++) {
                    outL[i] = (float)m_outBuffers[0][activeBufIdx][i] / 2147483648.0f;
                    outR[i] = (float)m_outBuffers[1][activeBufIdx][i] / 2147483648.0f;
                }
                m_ringBufferOut.write(outL, outR, curSize);
            }

            if (!m_running) break;

            // Long-term drift prevention: clamp ring buffers so latency never drifts over 2-3+ minutes
            size_t currentBuffered = m_ringBufferOut.availableRead();
            if (currentBuffered > (size_t)(m_bufferSize * 4 + framesNeeded)) {
                size_t excess = currentBuffered - (size_t)(m_bufferSize * 2 + framesNeeded);
                float dummyL[512], dummyR[512];
                while (excess > 0) {
                    size_t dChunk = (excess > 512) ? 512 : excess;
                    m_ringBufferOut.read(dummyL, dummyR, dChunk);
                    excess -= dChunk;
                }
            }

            size_t inBuffered = m_ringBufferIn.availableRead();
            if (inBuffered > (size_t)(m_bufferSize * 4)) {
                size_t excessIn = inBuffered - (size_t)(m_bufferSize * 2);
                float dummyL[512], dummyR[512];
                while (excessIn > 0) {
                    size_t dChunk = (excessIn > 512) ? 512 : excessIn;
                    m_ringBufferIn.read(dummyL, dummyR, dChunk);
                    excessIn -= dChunk;
                }
            }

            // 4. Deliver continuous audio from m_ringBufferOut to WASAPI Render Service
            if (m_hasRender && m_pRenderService && framesNeeded > 0) {
                BYTE* pDstData = NULL;
                HRESULT hrGet = m_pRenderService->GetBuffer(framesNeeded, &pDstData);
                if (hrGet == AUDCLNT_E_BUFFER_TOO_LARGE && !m_isExclusiveActive) {
                    UINT32 pad = 0;
                    if (SUCCEEDED(m_pRenderClient->GetCurrentPadding(&pad)) && totalFrames > pad) {
                        framesNeeded = totalFrames - pad;
                        if (framesNeeded > 0) {
                            hrGet = m_pRenderService->GetBuffer(framesNeeded, &pDstData);
                        }
                    }
                }

                if (SUCCEEDED(hrGet) && pDstData) {
                    UINT32 framesCopied = 0;
                    float playL[512], playR[512];
                    while (framesCopied < framesNeeded) {
                        UINT32 chunk = framesNeeded - framesCopied;
                        if (chunk > 512) chunk = 512;
                        m_ringBufferOut.read(playL, playR, chunk);

                        if (m_isRenderFloat) {
                            float* pDst = (float*)pDstData + (framesCopied * 2);
                            for (UINT32 i = 0; i < chunk; i++) {
                                pDst[i * 2 + 0] = playL[i];
                                pDst[i * 2 + 1] = playR[i];
                            }
                        } else if (m_renderFormat.Format.wBitsPerSample == 32) {
                            int32_t* pDst = (int32_t*)pDstData + (framesCopied * 2);
                            for (UINT32 i = 0; i < chunk; i++) {
                                float sL = playL[i];
                                float sR = playR[i];
                                if (sL > 1.0f) sL = 1.0f; else if (sL < -1.0f) sL = -1.0f;
                                if (sR > 1.0f) sR = 1.0f; else if (sR < -1.0f) sR = -1.0f;
                                pDst[i * 2 + 0] = (int32_t)(sL * 2147483647.0f);
                                pDst[i * 2 + 1] = (int32_t)(sR * 2147483647.0f);
                            }
                        } else if (m_renderFormat.Format.wBitsPerSample == 16) {
                            int16_t* pDst = (int16_t*)pDstData + (framesCopied * 2);
                            for (UINT32 i = 0; i < chunk; i++) {
                                float sL = playL[i];
                                float sR = playR[i];
                                if (sL > 1.0f) sL = 1.0f; else if (sL < -1.0f) sL = -1.0f;
                                if (sR > 1.0f) sR = 1.0f; else if (sR < -1.0f) sR = -1.0f;
                                pDst[i * 2 + 0] = (int16_t)(sL * 32767.0f);
                                pDst[i * 2 + 1] = (int16_t)(sR * 32767.0f);
                            }
                        }
                        framesCopied += chunk;
                    }
                    m_pRenderService->ReleaseBuffer(framesNeeded, 0);
                }
            }
        }
    }

    if (hAvrt) {
        AvRevertMmThreadCharacteristics(hAvrt);
    }
    AsioLog("audioThreadLoop stopped cleanly");
}

// ---------------------------------------------------------------- Config persistence
void CSMK37ProASIO::loadConfig() {
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\M-VAVE\\SMK-37 Pro ASIO", 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        DWORD dwVal = 0;
        DWORD dwSize = sizeof(dwVal);
        if (RegQueryValueExW(hKey, L"BufferSize", NULL, NULL, (LPBYTE)&dwVal, &dwSize) == ERROR_SUCCESS) {
            if (dwVal >= MIN_BUFFER_SIZE && dwVal <= MAX_BUFFER_SIZE) {
                m_bufferSize = dwVal;
                m_pendingBufferSize = dwVal;
            }
        }
        if (RegQueryValueExW(hKey, L"ExclusiveMode", NULL, NULL, (LPBYTE)&dwVal, &dwSize) == ERROR_SUCCESS) {
            m_exclusiveMode = (dwVal != 0);
        }
        RegCloseKey(hKey);
    }
}

void CSMK37ProASIO::saveConfig() {
    HKEY hKey;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\M-VAVE\\SMK-37 Pro ASIO", 0, NULL,
                       REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        DWORD dwVal = m_pendingBufferSize ? m_pendingBufferSize : m_bufferSize;
        RegSetValueExW(hKey, L"BufferSize", 0, REG_DWORD, (const BYTE*)&dwVal, sizeof(dwVal));
        dwVal = m_exclusiveMode ? 1 : 0;
        RegSetValueExW(hKey, L"ExclusiveMode", 0, REG_DWORD, (const BYTE*)&dwVal, sizeof(dwVal));
        RegCloseKey(hKey);
    }
}
