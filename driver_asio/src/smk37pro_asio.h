#ifndef __smk37pro_asio_h__
#define __smk37pro_asio_h__

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <avrt.h>
#include <functiondiscoverykeys_devpkey.h>
#include <stdio.h>
#include <string>
#include <vector>

#include "iasiodrv.h"

// Unique CLSID for M-VAVE SMK-37 Pro ASIO Driver:
// {7C38B80E-5AED-4B33-A751-6CE34EC4C701}
static const CLSID CLSID_SMK37Pro_ASIO = {
    0x7c38b80e, 0x5aed, 0x4b33, { 0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01 }
};

#define DRIVER_NAME "M-VAVE SMK-37 Pro ASIO"
#define DRIVER_DESC "M-VAVE SMK-37 Pro USB Audio ASIO Driver"
#define DRIVER_VERSION 1000 // 1.0.0

// Logging utility
void AsioLog(const char* fmt, ...);

#define NUM_INPUT_CHANNELS  2
#define NUM_OUTPUT_CHANNELS 2

#define DEFAULT_SAMPLE_RATE 44100.0
#define DEFAULT_BUFFER_SIZE 256
#define MIN_BUFFER_SIZE     32
#define MAX_BUFFER_SIZE     2048

// ---------------------------------------------------------------- AudioRingBuffer
class AudioRingBuffer {
public:
    AudioRingBuffer(size_t capacity = 65536)
        : m_capacity(capacity), m_readPos(0), m_writePos(0), m_count(0) {
        m_bufferL = new float[capacity]();
        m_bufferR = new float[capacity]();
        InitializeCriticalSection(&m_cs);
    }

    ~AudioRingBuffer() {
        delete[] m_bufferL;
        delete[] m_bufferR;
        DeleteCriticalSection(&m_cs);
    }

    void reset() {
        EnterCriticalSection(&m_cs);
        m_readPos = 0;
        m_writePos = 0;
        m_count = 0;
        memset(m_bufferL, 0, m_capacity * sizeof(float));
        memset(m_bufferR, 0, m_capacity * sizeof(float));
        LeaveCriticalSection(&m_cs);
    }

    size_t availableRead() {
        EnterCriticalSection(&m_cs);
        size_t count = m_count;
        LeaveCriticalSection(&m_cs);
        return count;
    }

    size_t availableWrite() {
        EnterCriticalSection(&m_cs);
        size_t avail = m_capacity - m_count;
        LeaveCriticalSection(&m_cs);
        return avail;
    }

    void write(const float* pL, const float* pR, size_t count) {
        EnterCriticalSection(&m_cs);
        for (size_t i = 0; i < count; i++) {
            m_bufferL[m_writePos] = pL ? pL[i] : 0.0f;
            m_bufferR[m_writePos] = pR ? pR[i] : 0.0f;
            m_writePos = (m_writePos + 1) % m_capacity;
            if (m_count < m_capacity) {
                m_count++;
            } else {
                // Buffer overflow: push read pointer forward
                m_readPos = (m_readPos + 1) % m_capacity;
            }
        }
        LeaveCriticalSection(&m_cs);
    }

    void writeSilence(size_t count) {
        EnterCriticalSection(&m_cs);
        for (size_t i = 0; i < count; i++) {
            m_bufferL[m_writePos] = 0.0f;
            m_bufferR[m_writePos] = 0.0f;
            m_writePos = (m_writePos + 1) % m_capacity;
            if (m_count < m_capacity) {
                m_count++;
            } else {
                m_readPos = (m_readPos + 1) % m_capacity;
            }
        }
        LeaveCriticalSection(&m_cs);
    }

    void read(float* pL, float* pR, size_t count) {
        EnterCriticalSection(&m_cs);
        for (size_t i = 0; i < count; i++) {
            if (m_count > 0) {
                if (pL) pL[i] = m_bufferL[m_readPos];
                if (pR) pR[i] = m_bufferR[m_readPos];
                m_readPos = (m_readPos + 1) % m_capacity;
                m_count--;
            } else {
                if (pL) pL[i] = 0.0f;
                if (pR) pR[i] = 0.0f;
            }
        }
        LeaveCriticalSection(&m_cs);
    }

private:
    size_t m_capacity;
    size_t m_readPos;
    size_t m_writePos;
    size_t m_count;
    float* m_bufferL;
    float* m_bufferR;
    CRITICAL_SECTION m_cs;
};

class CSMK37ProASIO : public IASIO {
public:
    CSMK37ProASIO();
    virtual ~CSMK37ProASIO();

    // IUnknown methods
    STDMETHODIMP QueryInterface(REFIID riid, LPVOID* ppvObj) override;
    STDMETHODIMP_(ULONG) AddRef() override;
    STDMETHODIMP_(ULONG) Release() override;

    // IASIO methods
    ASIOBool init(void *sysHandle) override;
    void getDriverName(char *name) override;
    long getDriverVersion() override;
    void getErrorMessage(char *string) override;
    ASIOError start() override;
    ASIOError stop() override;
    ASIOError getChannels(long *numInputChannels, long *numOutputChannels) override;
    ASIOError getLatencies(long *inputLatency, long *outputLatency) override;
    ASIOError getBufferSize(long *minSize, long *maxSize, long *preferredSize, long *granularity) override;
    ASIOError canSampleRate(ASIOSampleRate sampleRate) override;
    ASIOError getSampleRate(ASIOSampleRate *sampleRate) override;
    ASIOError setSampleRate(ASIOSampleRate sampleRate) override;
    ASIOError getClockSources(ASIOClockSource *clocks, long *numSources) override;
    ASIOError setClockSource(long reference) override;
    ASIOError getSamplePosition(ASIOSamples *sPos, ASIOTimeStamp *tStamp) override;
    ASIOError getChannelInfo(ASIOChannelInfo *info) override;
    ASIOError createBuffers(ASIOBufferInfo *bufferInfos, long numChannels, long bufferSize, ASIOCallbacks *callbacks) override;
    ASIOError disposeBuffers() override;
    ASIOError controlPanel() override;
    ASIOError future(long selector, void *opt) override;
    ASIOError outputReady() override;

    // Internal WASAPI Engine Methods
    bool initWASAPI();
    void closeWASAPI();
    static DWORD WINAPI AudioThreadEntry(LPVOID lpParam);
    void audioThreadLoop();

    // Configuration / Registry
    void loadConfig();
    void saveConfig();
    void requestReset() {
        if (m_callbacks && m_callbacks->asioMessage) {
            m_callbacks->asioMessage(1, 0, NULL, NULL); // kAsioResetRequest = 1
        }
    }
    void scheduleDeferredReset();

    // Diagnostics & GUI
    HWND m_hParentWnd;
    long m_bufferSize;
    long m_pendingBufferSize;
    long m_allocatedBufferSize;
    ASIOSampleRate m_sampleRate;
    bool m_exclusiveMode;
    std::wstring m_detectedDevName;
    bool m_deviceFound;

private:
    volatile LONG m_refCount;
    bool m_initialized;
    bool m_running;
    char m_errorMessage[128];

    // ASIO Buffers & Callbacks
    long m_numChannels;
    ASIOBufferInfo* m_bufferInfos;
    ASIOCallbacks* m_callbacks;
    long m_doubleBufferIndex;
    int64_t m_samplePosition;

    // Ping-pong allocated buffer memory (32-bit integer LSB)
    int32_t* m_inBuffers[NUM_INPUT_CHANNELS][2];
    int32_t* m_outBuffers[NUM_OUTPUT_CHANNELS][2];

    // Ring Buffers for continuous streaming
    AudioRingBuffer m_ringBufferOut;
    AudioRingBuffer m_ringBufferIn;

    // WASAPI COM Interfaces & Handles
    IMMDeviceEnumerator* m_pEnumerator;
    IMMDevice* m_pRenderDevice;
    IMMDevice* m_pCaptureDevice;
    IAudioClient* m_pRenderClient;
    IAudioClient* m_pCaptureClient;
    IAudioRenderClient* m_pRenderService;
    IAudioCaptureClient* m_pCaptureService;

    HANDLE m_hRenderEvent;
    HANDLE m_hCaptureEvent;
    HANDLE m_hStopEvent;
    HANDLE m_hAudioThread;

    WAVEFORMATEXTENSIBLE m_renderFormat;
    WAVEFORMATEXTENSIBLE m_captureFormat;
    bool m_hasCapture;
    bool m_hasRender;
    bool m_isExclusiveActive;
    bool m_isRenderFloat;
    bool m_isCaptureFloat;

    CRITICAL_SECTION m_lock;
};

#endif // __smk37pro_asio_h__
