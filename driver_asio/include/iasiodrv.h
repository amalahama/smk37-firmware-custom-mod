#ifndef __iasiodrv_h__
#define __iasiodrv_h__

#include <unknwn.h>
#include "asio.h"

// Steinberg ASIO COM Interface IID: {3F484C24-76B8-11D1-8B06-00A024406D59}
// {3F484C24-76B8-11D1-8B06-00A024406D59}
static const IID IID_IASIO = {
    0x3f484c24, 0x76b8, 0x11d1, { 0x8b, 0x06, 0x00, 0xa0, 0x24, 0x40, 0x6d, 0x59 }
};

#undef INTERFACE
#define INTERFACE IASIO

DECLARE_INTERFACE_(IASIO, IUnknown) {
    // IUnknown methods
    STDMETHOD(QueryInterface)(THIS_ REFIID riid, LPVOID* ppvObj) PURE;
    STDMETHOD_(ULONG, AddRef)(THIS) PURE;
    STDMETHOD_(ULONG, Release)(THIS) PURE;

    // IASIO methods
    STDMETHOD_(ASIOBool, init)(THIS_ void *sysHandle) PURE;
    STDMETHOD_(void, getDriverName)(THIS_ char *name) PURE;
    STDMETHOD_(long, getDriverVersion)(THIS) PURE;
    STDMETHOD_(void, getErrorMessage)(THIS_ char *string) PURE;
    STDMETHOD_(ASIOError, start)(THIS) PURE;
    STDMETHOD_(ASIOError, stop)(THIS) PURE;
    STDMETHOD_(ASIOError, getChannels)(THIS_ long *numInputChannels, long *numOutputChannels) PURE;
    STDMETHOD_(ASIOError, getLatencies)(THIS_ long *inputLatency, long *outputLatency) PURE;
    STDMETHOD_(ASIOError, getBufferSize)(THIS_ long *minSize, long *maxSize, long *preferredSize, long *granularity) PURE;
    STDMETHOD_(ASIOError, canSampleRate)(THIS_ ASIOSampleRate sampleRate) PURE;
    STDMETHOD_(ASIOError, getSampleRate)(THIS_ ASIOSampleRate *sampleRate) PURE;
    STDMETHOD_(ASIOError, setSampleRate)(THIS_ ASIOSampleRate sampleRate) PURE;
    STDMETHOD_(ASIOError, getClockSources)(THIS_ ASIOClockSource *clocks, long *numSources) PURE;
    STDMETHOD_(ASIOError, setClockSource)(THIS_ long reference) PURE;
    STDMETHOD_(ASIOError, getSamplePosition)(THIS_ ASIOSamples *sPos, ASIOTimeStamp *tStamp) PURE;
    STDMETHOD_(ASIOError, getChannelInfo)(THIS_ ASIOChannelInfo *info) PURE;
    STDMETHOD_(ASIOError, createBuffers)(THIS_ ASIOBufferInfo *bufferInfos, long numChannels, long bufferSize, ASIOCallbacks *callbacks) PURE;
    STDMETHOD_(ASIOError, disposeBuffers)(THIS) PURE;
    STDMETHOD_(ASIOError, controlPanel)(THIS) PURE;
    STDMETHOD_(ASIOError, future)(THIS_ long selector, void *opt) PURE;
    STDMETHOD_(ASIOError, outputReady)(THIS) PURE;
};

#endif // __iasiodrv_h__
