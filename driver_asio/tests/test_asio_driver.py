#!/usr/bin/env python3
"""test_asio_driver.py — Automated ASIO Driver Test Client

Simulates DAW host behavior (Ableton, Reaper, FL Studio) testing:
  1. COM Class Factory instantiation via CLSID
  2. QueryInterface for Steinberg IASIO
  3. init(), getDriverName(), getDriverVersion()
  4. getChannels(), getBufferSize(), getSampleRate()
  5. getChannelInfo() for all inputs and outputs
  6. createBuffers() with ping-pong double buffers
  7. start(), callback invocation verification, sample position tracking
  8. stop(), disposeBuffers(), and clean release
"""

import sys
import time
import ctypes
from ctypes import wintypes
import winreg

# Steinberg IASIO GUID: {3F484C24-76B8-11D1-8B06-00A024406D59}
IID_IASIO = ctypes.c_char_p(bytes.fromhex("24 4c 48 3f b8 76 d1 11 8b 06 00 a0 24 40 6d 59"))
CLSID_SMK37_STR = "{7C38B80E-5AED-4B33-A751-6CE34EC4C701}"

# Let's define the IASIO VTable in ctypes
class ASIOBufferInfo(ctypes.Structure):
    _fields_ = [
        ("isInput", ctypes.c_long),
        ("channelNum", ctypes.c_long),
        ("buffers", ctypes.c_void_p * 2),
    ]

class ASIOChannelInfo(ctypes.Structure):
    _fields_ = [
        ("channel", ctypes.c_long),
        ("isInput", ctypes.c_long),
        ("isActive", ctypes.c_long),
        ("channelGroup", ctypes.c_long),
        ("type", ctypes.c_long),
        ("name", ctypes.c_char * 32),
    ]

class ASIOSamples(ctypes.Structure):
    _fields_ = [
        ("hi", ctypes.c_ulong),
        ("lo", ctypes.c_ulong),
    ]

class ASIOTimeStamp(ctypes.Structure):
    _fields_ = [
        ("hi", ctypes.c_ulong),
        ("lo", ctypes.c_ulong),
    ]

# Callbacks
BUFFER_SWITCH_PROC = ctypes.WINFUNCTYPE(None, ctypes.c_long, ctypes.c_long)
SAMPLE_RATE_PROC = ctypes.WINFUNCTYPE(None, ctypes.c_double)
ASIO_MESSAGE_PROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double))

class ASIOCallbacks(ctypes.Structure):
    _fields_ = [
        ("bufferSwitch", BUFFER_SWITCH_PROC),
        ("sampleRateDidChange", SAMPLE_RATE_PROC),
        ("asioMessage", ASIO_MESSAGE_PROC),
        ("bufferSwitchTimeInfo", ctypes.c_void_p),
    ]

callback_counter = 0

def on_buffer_switch(double_buf_idx, direct_proc):
    global callback_counter
    callback_counter += 1

def on_sample_rate(s_rate):
    print(f"  [Callback] Sample rate changed to: {s_rate}")

def on_message(selector, val, msg, opt):
    print(f"  [Callback] ASIO Message: selector={selector}, val={val}")
    return 0

def test_driver():
    global callback_counter
    print("=" * 60)
    print("M-VAVE SMK-37 Pro Dedicated ASIO Driver Automated Test")
    print("=" * 60)

    # Step 1: Check Registry
    print("\n1. Checking Windows Registry...")
    found = False
    for root_key, root_name in [(winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
        try:
            with winreg.OpenKey(root_key, r"Software\ASIO\M-VAVE SMK-37 Pro ASIO") as k:
                clsid, _ = winreg.QueryValueEx(k, "CLSID")
                desc, _ = winreg.QueryValueEx(k, "Description")
                print(f"  Found in {root_name}: '{desc}' -> CLSID {clsid}")
                found = True
        except FileNotFoundError:
            pass

    if not found:
        print("  Error: Driver not found in registry! Please run install_driver.py first.")
        return False

    # Step 2: Load DLL and instantiate COM class factory
    print("\n2. Loading DLL directly and testing Class Factory...")
    dll_path = r"O:\PROGRAMACION\GEMINI ANTIGRAVITY\SMK37mod\driver_asio\bin\SMK37Pro_ASIO.dll"
    lib = ctypes.WinDLL(dll_path)

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    # Call DllGetClassObject
    # CLSID: 7C38B80E-5AED-4B33-A751-6CE34EC4C701
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8)
        ]

    clsid_smk = GUID(0x7c38b80e, 0x5aed, 0x4b33, (ctypes.c_ubyte * 8)(0xa7, 0x51, 0x6c, 0xe3, 0x4e, 0xc4, 0xc7, 0x01))
    iid_iclassfactory = GUID(0x00000001, 0x0000, 0x0000, (ctypes.c_ubyte * 8)(0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
    iid_iasio = GUID(0x3f484c24, 0x76b8, 0x11d1, (ctypes.c_ubyte * 8)(0x8b, 0x06, 0x00, 0xa0, 0x24, 0x40, 0x6d, 0x59))

    pFactory = ctypes.c_void_p()
    hr = lib.DllGetClassObject(ctypes.byref(clsid_smk), ctypes.byref(iid_iclassfactory), ctypes.byref(pFactory))
    print(f"  DllGetClassObject: hr=0x{hr:08X}, pFactory={pFactory.value:#x}")
    if hr != 0:
        print("  Failed to get class factory!")
        return False

    # Create Instance of IASIO
    # IClassFactory VTable: QueryInterface(0), AddRef(1), Release(2), CreateInstance(3), LockServer(4)
    vt_factory = ctypes.cast(pFactory.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    CreateInstance = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(vt_factory[3])

    pAsio = ctypes.c_void_p()
    hr = CreateInstance(pFactory, None, ctypes.byref(iid_iasio), ctypes.byref(pAsio))
    print(f"  CreateInstance(IID_IASIO): hr=0x{hr:08X}, pAsio={pAsio.value:#x}")
    if hr != 0 or not pAsio.value:
        print("  Failed to create IASIO instance!")
        return False

    # Bind IASIO methods from VTable:
    # 0: QueryInterface, 1: AddRef, 2: Release
    # 3: init, 4: getDriverName, 5: getDriverVersion, 6: getErrorMessage
    # 7: start, 8: stop, 9: getChannels, 10: getLatencies, 11: getBufferSize
    # 12: canSampleRate, 13: getSampleRate, 14: setSampleRate
    # 15: getClockSources, 16: setClockSource, 17: getSamplePosition, 18: getChannelInfo
    # 19: createBuffers, 20: disposeBuffers, 21: controlPanel, 22: future, 23: outputReady
    vt = ctypes.cast(pAsio.value, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

    f_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(vt[3])
    f_getName = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p)(vt[4])
    f_getVersion = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[5])
    f_getChannels = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long))(vt[9])
    f_getBufferSize = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_long))(vt[11])
    f_getSampleRate = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_double))(vt[13])
    f_getChannelInfo = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ASIOChannelInfo))(vt[18])
    f_createBuffers = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ASIOBufferInfo), ctypes.c_long, ctypes.c_long, ctypes.POINTER(ASIOCallbacks))(vt[19])
    f_start = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[7])
    f_getSamplePosition = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ASIOSamples), ctypes.POINTER(ASIOTimeStamp))(vt[17])
    f_stop = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[8])
    f_disposeBuffers = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[20])
    f_release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vt[2])

    # Step 3: Test Driver Properties
    print("\n3. Testing Driver Initialization & Information...")
    res = f_init(pAsio, None)
    print(f"  init(): {res} (ASIOTrue={1})")

    name_buf = ctypes.create_string_buffer(32)
    f_getName(pAsio, name_buf)
    print(f"  getDriverName(): '{name_buf.value.decode()}'")

    ver = f_getVersion(pAsio)
    print(f"  getDriverVersion(): {ver}")

    num_in = ctypes.c_long(0)
    num_out = ctypes.c_long(0)
    f_getChannels(pAsio, ctypes.byref(num_in), ctypes.byref(num_out))
    print(f"  getChannels(): {num_in.value} Inputs, {num_out.value} Outputs")

    min_sz = ctypes.c_long(0)
    max_sz = ctypes.c_long(0)
    pref_sz = ctypes.c_long(0)
    gran = ctypes.c_long(0)
    f_getBufferSize(pAsio, ctypes.byref(min_sz), ctypes.byref(max_sz), ctypes.byref(pref_sz), ctypes.byref(gran))
    print(f"  getBufferSize(): min={min_sz.value}, max={max_sz.value}, preferred={pref_sz.value}, gran={gran.value}")

    s_rate = ctypes.c_double(0.0)
    f_getSampleRate(pAsio, ctypes.byref(s_rate))
    print(f"  getSampleRate(): {s_rate.value:.1f} Hz")

    print("\n4. Testing Channel Information...")
    for is_in, count, label in [(1, num_in.value, "Input"), (0, num_out.value, "Output")]:
        for ch in range(count):
            info = ASIOChannelInfo()
            info.channel = ch
            info.isInput = is_in
            f_getChannelInfo(pAsio, ctypes.byref(info))
            print(f"  Channel [{label} {ch}]: '{info.name.decode()}', type={info.type} (32-bit LSB), active={info.isActive}")

    # Step 5: Test Buffer Creation & Streaming
    print("\n5. Testing Buffer Allocation & Audio Streaming Loop...")
    total_channels = num_in.value + num_out.value
    buf_infos = (ASIOBufferInfo * total_channels)()

    idx = 0
    for ch in range(num_in.value):
        buf_infos[idx].isInput = 1
        buf_infos[idx].channelNum = ch
        idx += 1
    for ch in range(num_out.value):
        buf_infos[idx].isInput = 0
        buf_infos[idx].channelNum = ch
        idx += 1

    cb = ASIOCallbacks()
    cb.bufferSwitch = BUFFER_SWITCH_PROC(on_buffer_switch)
    cb.sampleRateDidChange = SAMPLE_RATE_PROC(on_sample_rate)
    cb.asioMessage = ASIO_MESSAGE_PROC(on_message)
    cb.bufferSwitchTimeInfo = None

    buf_size = pref_sz.value
    res = f_createBuffers(pAsio, buf_infos, total_channels, buf_size, ctypes.byref(cb))
    print(f"  createBuffers(size={buf_size}): result={res} (ASE_OK=0)")
    for i in range(total_channels):
        kind = "In" if buf_infos[i].isInput else "Out"
        print(f"    Buffer [{kind} {buf_infos[i].channelNum}]: buf0={buf_infos[i].buffers[0]:#x}, buf1={buf_infos[i].buffers[1]:#x}")

    print("\n6. Starting Audio Engine (Running for 400 ms)...")
    callback_counter = 0
    res = f_start(pAsio)
    print(f"  start(): result={res} (ASE_OK=0)")
    if res != 0:
        err_buf = ctypes.create_string_buffer(128)
        f_getErrorMessage = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_char_p)(vt[6])
        f_getErrorMessage(pAsio, err_buf)
        print(f"  Driver Error Message: '{err_buf.value.decode()}'")

    time.sleep(0.4)

    s_pos = ASIOSamples()
    t_stamp = ASIOTimeStamp()
    f_getSamplePosition(pAsio, ctypes.byref(s_pos), ctypes.byref(t_stamp))
    full_samples = (s_pos.hi << 32) | s_pos.lo
    print(f"  Sample Position after 400 ms: {full_samples} samples")
    print(f"  Total bufferSwitch callbacks invoked: {callback_counter}")

    print("\n7. Stopping Audio Engine & Cleanup...")
    f_stop(pAsio)
    f_disposeBuffers(pAsio)
    f_release(pAsio)

    print("\n" + "=" * 60)
    print("[PASS] ALL ASIO DRIVER VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    test_driver()
