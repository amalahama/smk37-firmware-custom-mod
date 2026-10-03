import sys
import time
import ctypes
from ctypes import wintypes

winmm = ctypes.windll.winmm
HMIDIIN = wintypes.HANDLE
HMIDIOUT = wintypes.HANDLE
LPHMIDIIN = ctypes.POINTER(HMIDIIN)
LPHMIDIOUT = ctypes.POINTER(HMIDIOUT)
DWORD_PTR = ctypes.c_size_t

class MIDIHDR(ctypes.Structure):
    pass
MIDIHDR._fields_ = [
    ('lpData', ctypes.c_char_p),
    ('dwBufferLength', wintypes.DWORD),
    ('dwBytesRecorded', wintypes.DWORD),
    ('dwUser', ctypes.c_void_p),
    ('dwFlags', wintypes.DWORD),
    ('lpNext', ctypes.POINTER(MIDIHDR)),
    ('reserved', ctypes.c_void_p),
    ('dwOffset', wintypes.DWORD),
    ('dwReserved', ctypes.c_void_p * 4),
]

winmm.midiInOpen.argtypes = [LPHMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]
winmm.midiInOpen.restype = wintypes.UINT
winmm.midiOutOpen.argtypes = [LPHMIDIOUT, wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]
winmm.midiOutOpen.restype = wintypes.UINT
winmm.midiInPrepareHeader.argtypes = [HMIDIIN, ctypes.c_void_p, wintypes.UINT]
winmm.midiInPrepareHeader.restype = wintypes.UINT
winmm.midiInAddBuffer.argtypes = [HMIDIIN, ctypes.c_void_p, wintypes.UINT]
winmm.midiInAddBuffer.restype = wintypes.UINT
winmm.midiInStart.argtypes = [HMIDIIN]
winmm.midiInStart.restype = wintypes.UINT
winmm.midiInStop.argtypes = [HMIDIIN]
winmm.midiInStop.restype = wintypes.UINT
winmm.midiInReset.argtypes = [HMIDIIN]
winmm.midiInReset.restype = wintypes.UINT
winmm.midiInClose.argtypes = [HMIDIIN]
winmm.midiInClose.restype = wintypes.UINT
winmm.midiInUnprepareHeader.argtypes = [HMIDIIN, ctypes.c_void_p, wintypes.UINT]
winmm.midiInUnprepareHeader.restype = wintypes.UINT
winmm.midiOutPrepareHeader.argtypes = [HMIDIOUT, ctypes.c_void_p, wintypes.UINT]
winmm.midiOutPrepareHeader.restype = wintypes.UINT
winmm.midiOutLongMsg.argtypes = [HMIDIOUT, ctypes.c_void_p, wintypes.UINT]
winmm.midiOutLongMsg.restype = wintypes.UINT
winmm.midiOutUnprepareHeader.argtypes = [HMIDIOUT, ctypes.c_void_p, wintypes.UINT]
winmm.midiOutUnprepareHeader.restype = wintypes.UINT
winmm.midiOutReset.argtypes = [HMIDIOUT]
winmm.midiOutReset.restype = wintypes.UINT
winmm.midiOutClose.argtypes = [HMIDIOUT]
winmm.midiOutClose.restype = wintypes.UINT

rx = []
def _cb(h, msg, inst, p1, p2):
    if msg == 0x3C4: # MIM_LONGDATA
        hdr_ptr = ctypes.cast(p1, ctypes.POINTER(MIDIHDR))
        hdr = hdr_ptr.contents
        if hdr.dwBytesRecorded > 0:
            rx.append(ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded))

MidiInProc = ctypes.WINFUNCTYPE(None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)
cb_inst = MidiInProc(_cb)
cb_ptr = ctypes.cast(cb_inst, ctypes.c_void_p).value

h_in = HMIDIIN()
h_out = HMIDIOUT()

# Input 0: SMK-37 Pro Midi, Output 1: SMK-37 Pro Midi
r1 = winmm.midiInOpen(ctypes.byref(h_in), 0, cb_ptr, 0, 0x00030000)
r2 = winmm.midiOutOpen(ctypes.byref(h_out), 1, 0, 0, 0)
print(f"Opened: in_res={r1}, out_res={r2}")

bufs = []
for _ in range(8):
    b = ctypes.create_string_buffer(1024)
    hdr = MIDIHDR()
    hdr.lpData = ctypes.cast(b, ctypes.c_char_p)
    hdr.dwBufferLength = 1024
    winmm.midiInPrepareHeader(h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
    winmm.midiInAddBuffer(h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
    bufs.append((b, hdr))

winmm.midiInStart(h_in)

HS_QUERY = bytes([0xF0, 0x00, 0x32, 0x45, 0x00, 0x00, 0x00, 0x40, 0x7F, 0xF7])
out_b = ctypes.create_string_buffer(HS_QUERY)
out_hdr = MIDIHDR()
out_hdr.lpData = ctypes.cast(out_b, ctypes.c_char_p)
out_hdr.dwBufferLength = len(HS_QUERY)
winmm.midiOutPrepareHeader(h_out, ctypes.byref(out_hdr), ctypes.sizeof(out_hdr))
winmm.midiOutLongMsg(h_out, ctypes.byref(out_hdr), ctypes.sizeof(out_hdr))

t0 = time.time()
while not (out_hdr.dwFlags & 0x00000001):
    if time.time() - t0 > 1.0:
        break
    time.sleep(0.001)

winmm.midiOutUnprepareHeader(h_out, ctypes.byref(out_hdr), ctypes.sizeof(out_hdr))

print("Waiting for response from SMK-37 Pro...")
t_end = time.time() + 2.0
while time.time() < t_end and not rx:
    time.sleep(0.02)

print(f"Received {len(rx)} packets:")
for p in rx:
    print(f"  Hex: {p.hex()}")
    # try unpack7
    acc, nb, s = 0, 0, bytearray()
    for b in p[1:-1]:
        acc |= b << nb
        nb += 7
        while nb >= 8:
            s.append(acc & 0xFF)
            acc >>= 8
            nb -= 8
    print(f"  Decoded: {repr(bytes(s))}")

winmm.midiInStop(h_in)
winmm.midiInReset(h_in)
for b, hdr in bufs:
    winmm.midiInUnprepareHeader(h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
winmm.midiInClose(h_in)
winmm.midiOutReset(h_out)
winmm.midiOutClose(h_out)
print("Finished test cleanly.")
