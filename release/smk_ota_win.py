#!/usr/bin/env python3
"""smk_ota_win.py — Windows USB-MIDI OTA Flasher for M-VAVE SMK-37 Pro / Elite / FM-1

Uses native Windows Multimedia API (winmm.dll via ctypes) with zero external C/C++ dependencies.
Implements the M-VAVE / JieLi USB-MIDI SysEx OTA protocol:
  Stage 1 (Normal Mode):
    1. Handshake query (0xF0 00 32 45 00 00 00 40 7F F7) -> get model/version
    2. Upgrade trigger (0xF0 22 24 35 7F F7)
    3. Serve verification read requests until 0xE0000000 ("verification done")
    4. Device reboots into OTA bootloader
  Stage 2 (Bootloader Mode):
    5. Reconnect to re-enumerated USB-MIDI device
    6. Handshake + Upgrade trigger
    7. Stream 8->7 bitstream firmware chunks until 0xF0000000 ("flash complete")
    8. Device writes Flash and boots into updated firmware
"""

import sys
import os
import time
import struct
import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path

try:
    from tools.unpack_smk import deinterleave_fwsc
except ImportError:
    try:
        from unpack_smk import deinterleave_fwsc
    except ImportError:
        def deinterleave_fwsc(raw_bytes: bytes):
            num_blocks = 0
            markers = []
            total_possible = len(raw_bytes) // 0x30
            for i in range(total_possible):
                val = raw_bytes[i * 0x30 + 0x2F]
                if i < 20 or val == 0x7D:
                    num_blocks = i + 1
                    markers.append(val)
                else:
                    break
            logical = bytearray()
            for i in range(num_blocks):
                logical += raw_bytes[i * 0x30 : i * 0x30 + 0x2F]
            logical += raw_bytes[num_blocks * 0x30 :]
            return bytes(logical), markers, num_blocks


# ---------------------------------------------------------------- Constants
HS_QUERY = bytes([0xF0, 0x00, 0x32, 0x45, 0x00, 0x00, 0x00, 0x40, 0x7F, 0xF7])
UPGRADE_CMD = bytes([0xF0, 0x22, 0x24, 0x35, 0x7F, 0xF7])
MAXDATA = 512
REQ_TIMEOUT = 12.0


# ---------------------------------------------------------------- Bitstream 7/8 codec
def pack7(data: bytes) -> bytes:
    out = bytearray()
    acc = 0
    nb = 0
    for b in data:
        acc |= b << nb
        nb += 8
        while nb >= 7:
            out.append(acc & 0x7F)
            acc >>= 7
            nb -= 7
    if nb:
        out.append(acc & 0x7F)
    return bytes(out)


def unpack7(s: bytes) -> bytes:
    out = bytearray()
    acc = 0
    nb = 0
    for b in s:
        acc |= b << nb
        nb += 7
        while nb >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nb -= 8
    return bytes(out)


def build_response(addr: int, data: bytes, req_len: int = None, flashtype: int = 0) -> bytes:
    if req_len is None:
        req_len = len(data)
    body = (
        b"\x00\x59\x30"
        + (req_len + 8).to_bytes(3, "little")
        + bytes([flashtype])
        + addr.to_bytes(4, "little")
        + req_len.to_bytes(3, "little")
        + data
    )
    chk = (~sum(body[6:])) & 0xFF
    return b"\xF0" + pack7(body + bytes([chk])) + b"\xF7"


def build_success(addr: int) -> bytes:
    return build_response(addr, b"success\x00")


def parse_request(pkt: bytes):
    if len(pkt) < 4 or pkt[0] != 0xF0 or pkt[-1] != 0xF7:
        return None
    u = unpack7(pkt[1:-1])
    if len(u) != 15 or u[:3] != b"\x00\x59\x30":
        return None
    body_len = int.from_bytes(u[3:6], "little")
    if body_len != 8 or u[-1] != ((~sum(u[6:-1])) & 0xFF):
        return None
    fl = u[6]
    addr = int.from_bytes(u[7:11], "little")
    ln = int.from_bytes(u[11:14], "little")
    return (fl, addr, ln)


def parse_handshake_identity(pkt: bytes):
    if len(pkt) < 4 or pkt[0] != 0xF0 or pkt[-1] != 0xF7:
        return None
    decoded = unpack7(pkt[1:-1])
    if len(decoded) != 34 or decoded[:3] != b"\x00\x59\x11":
        return None
    body_len = int.from_bytes(decoded[3:6], "little")
    if body_len != 27:
        return None

    raw_str = decoded[6:33].split(b'\x00')[0].decode('ascii', errors='replace')
    return raw_str


# ---------------------------------------------------------------- Windows winmm.dll
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

class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [
        ('wMid', wintypes.WORD),
        ('wPid', wintypes.WORD),
        ('vDriverVersion', wintypes.DWORD),
        ('szPname', wintypes.WCHAR * 32),
        ('dwSupport', wintypes.DWORD),
    ]

class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ('wMid', wintypes.WORD),
        ('wPid', wintypes.WORD),
        ('vDriverVersion', wintypes.DWORD),
        ('szPname', wintypes.WCHAR * 32),
        ('wTechnology', wintypes.WORD),
        ('wVoices', wintypes.WORD),
        ('wNotes', wintypes.WORD),
        ('wChannelMask', wintypes.WORD),
        ('dwSupport', wintypes.DWORD),
    ]

# WinMM Prototypes
MidiInProc = ctypes.WINFUNCTYPE(None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)

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


def list_midi_devices():
    inputs = []
    num_in = winmm.midiInGetNumDevs()
    for i in range(num_in):
        caps = MIDIINCAPSW()
        winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        inputs.append((i, caps.szPname))

    outputs = []
    num_out = winmm.midiOutGetNumDevs()
    for i in range(num_out):
        caps = MIDIOUTCAPSW()
        winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        outputs.append((i, caps.szPname))

    return inputs, outputs


def find_smk_ports():
    inputs, outputs = list_midi_devices()
    priority_keywords = ["smk-37 pro midi", "smk-37", "smk", "m-vave", "sinco", "ota-"]
    
    in_idx, in_name = None, None
    for kw in priority_keywords:
        for idx, name in inputs:
            n_lower = name.lower()
            if kw in n_lower and "midiin2" not in n_lower and "midiin3" not in n_lower:
                in_idx, in_name = idx, name
                break
        if in_idx is not None:
            break

    if in_idx is None:
        for kw in priority_keywords:
            for idx, name in inputs:
                if kw in name.lower():
                    in_idx, in_name = idx, name
                    break
            if in_idx is not None:
                break

    out_idx, out_name = None, None
    for kw in priority_keywords:
        for idx, name in outputs:
            n_lower = name.lower()
            if kw in n_lower and "midiout2" not in n_lower and "midiout3" not in n_lower:
                out_idx, out_name = idx, name
                break
        if out_idx is not None:
            break

    if out_idx is None:
        for kw in priority_keywords:
            for idx, name in outputs:
                if kw in name.lower():
                    out_idx, out_name = idx, name
                    break
            if out_idx is not None:
                break

    return (in_idx, in_name), (out_idx, out_name)


def wait_for_device(timeout: float = 15.0):
    t_end = time.time() + timeout
    while time.time() < t_end:
        (in_id, in_name), (out_id, out_name) = find_smk_ports()
        if in_id is not None and out_id is not None:
            return (in_id, in_name), (out_id, out_name)
        time.sleep(0.5)
    return (None, None), (None, None)


class WinMidiSession:
    def __init__(self, in_id: int, out_id: int):
        self.in_id = in_id
        self.out_id = out_id
        self.h_in = HMIDIIN()
        self.h_out = HMIDIOUT()
        self.rx_queue = []
        self.in_buffers = []

        # Callback function for MIDI input
        self._callback = MidiInProc(self._midi_callback)
        cb_ptr = ctypes.cast(self._callback, ctypes.c_void_p).value

        res = winmm.midiInOpen(ctypes.byref(self.h_in), in_id, cb_ptr, 0, 0x00030000) # CALLBACK_FUNCTION
        if res != 0:
            raise RuntimeError(f"Failed to open MIDI In device {in_id} (error {res})")

        res = winmm.midiOutOpen(ctypes.byref(self.h_out), out_id, 0, 0, 0)
        if res != 0:
            winmm.midiInClose(self.h_in)
            self.h_in = None
            raise RuntimeError(f"Failed to open MIDI Out device {out_id} (error {res})")

        # Prepare 16 SysEx input buffers (1024 bytes each)
        for _ in range(16):
            buf = ctypes.create_string_buffer(1024)
            hdr = MIDIHDR()
            hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
            hdr.dwBufferLength = 1024
            hdr.dwBytesRecorded = 0
            hdr.dwFlags = 0
            winmm.midiInPrepareHeader(self.h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.midiInAddBuffer(self.h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
            self.in_buffers.append((buf, hdr))

        winmm.midiInStart(self.h_in)

    def _midi_callback(self, hMidiIn, wMsg, dwInstance, dwParam1, dwParam2):
        MIM_LONGDATA = 0x3C4
        if wMsg == MIM_LONGDATA:
            hdr = ctypes.cast(dwParam1, ctypes.POINTER(MIDIHDR)).contents
            if hdr.dwBytesRecorded > 0:
                data = ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded)
                self.rx_queue.append(data)

    def _recycle_buffers(self):
        if not self.h_in:
            return
        for buf, hdr in self.in_buffers:
            if hdr.dwFlags & 0x00000001: # MHDR_DONE
                hdr.dwBytesRecorded = 0
                hdr.dwFlags &= ~0x00000001
                winmm.midiInAddBuffer(self.h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))

    def send_sysex(self, data: bytes):
        if not self.h_out:
            return
        buf = ctypes.create_string_buffer(data)
        hdr = MIDIHDR()
        hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
        hdr.dwBufferLength = len(data)
        hdr.dwBytesRecorded = len(data)
        hdr.dwFlags = 0

        winmm.midiOutPrepareHeader(self.h_out, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.midiOutLongMsg(self.h_out, ctypes.byref(hdr), ctypes.sizeof(hdr))

        # Wait until sent with timeout
        t0 = time.time()
        while not (hdr.dwFlags & 0x00000001):
            if time.time() - t0 > 2.0:
                break
            time.sleep(0.001)

        winmm.midiOutUnprepareHeader(self.h_out, ctypes.byref(hdr), ctypes.sizeof(hdr))

    def recv_sysex(self, timeout: float = 1.0) -> bytes:
        t_end = time.time() + timeout
        while time.time() < t_end:
            self._recycle_buffers()
            if self.rx_queue:
                return self.rx_queue.pop(0)
            time.sleep(0.002)
        return None

    def close(self):
        if hasattr(self, 'h_in') and self.h_in:
            winmm.midiInStop(self.h_in)
            winmm.midiInReset(self.h_in)
            for buf, hdr in self.in_buffers:
                winmm.midiInUnprepareHeader(self.h_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.midiInClose(self.h_in)
            self.h_in = None

        if hasattr(self, 'h_out') and self.h_out:
            winmm.midiOutReset(self.h_out)
            winmm.midiOutClose(self.h_out)
            self.h_out = None


def cmd_scan():
    print("=" * 60)
    print("  Scanning Windows MIDI Devices...")
    print("=" * 60)
    inputs, outputs = list_midi_devices()
    print("\nMIDI Inputs:")
    for i, name in inputs:
        print(f"  [{i}] {name}")
    print("\nMIDI Outputs:")
    for i, name in outputs:
        print(f"  [{i}] {name}")

    (in_id, in_name), (out_id, out_name) = find_smk_ports()
    if in_id is not None and out_id is not None:
        print(f"\n[FOUND] Target device detected:")
        print(f"  Input:  [{in_id}] {in_name}")
        print(f"  Output: [{out_id}] {out_name}")

        try:
            sess = WinMidiSession(in_id, out_id)
            print("  Querying device identity...")
            sess.send_sysex(HS_QUERY)
            resp = sess.recv_sysex(timeout=1.5)
            sess.close()
            if resp:
                ident = parse_handshake_identity(resp)
                print(f"  Device identity: {ident}")
            else:
                print("  No response to handshake query (device may be in standard MIDI mode or busy).")
        except Exception as e:
            print(f"  Query error: {e}")
    else:
        print("\n[INFO] No SMK-37 Pro / M-VAVE MIDI devices detected.")
        print("Please ensure your keyboard is plugged in via USB and powered ON.")


def cmd_flash(fwsc_file: Path, in_override: int = None, out_override: int = None):
    if not fwsc_file.exists():
        print(f"Error: File not found: {fwsc_file}")
        sys.exit(1)

    print("=" * 65)
    print("  M-VAVE SMK-37 Pro USB-MIDI OTA Firmware Flasher")
    print("=" * 65)
    print(f"Firmware image: {fwsc_file.name}")
    raw_data = fwsc_file.read_bytes()
    logical_image, markers, num_blocks = deinterleave_fwsc(raw_data)
    print(f"  Deinterleaved: {num_blocks} blocks, {len(logical_image)} logical bytes.")

    if in_override is not None and out_override is not None:
        in_id, out_id = in_override, out_override
        in_name = f"Port {in_id}"
        out_name = f"Port {out_id}"
    else:
        (in_id, in_name), (out_id, out_name) = find_smk_ports()
        if in_id is None or out_id is None:
            print("Error: No SMK-37 Pro MIDI device detected! Connect the keyboard via USB.")
            sys.exit(1)

    print(f"Connecting to In:[{in_id}] {in_name} / Out:[{out_id}] {out_name}...")
    sess = WinMidiSession(in_id, out_id)

    stage1_done = False
    stage2_done = False

    try:
        print("\n--- STAGE 1: Handshake & Verification ---")
        sess.send_sysex(HS_QUERY)
        resp = sess.recv_sysex(timeout=2.0)
        if resp:
            ident = parse_handshake_identity(resp)
            print(f"  Current device: {ident}")

        print("  Sending upgrade trigger to device...")
        sess.send_sysex(UPGRADE_CMD)
        time.sleep(0.5)

        last_req_time = time.time()
        served_count = 0

        while True:
            pkt = sess.recv_sysex(timeout=0.1)
            if pkt:
                req = parse_request(pkt)
                if req:
                    fl, addr, req_len = req
                    last_req_time = time.time()

                    if addr == 0xE0000000:
                        print("\n  [STAGE 1 VERIFIED] Device verified package header.")
                        sess.send_sysex(build_success(addr))
                        stage1_done = True
                        break
                    elif addr == 0xF0000000:
                        print("\n  [STAGE 2 COMPLETE] Device finished writing flash.")
                        sess.send_sysex(build_success(addr))
                        stage2_done = True
                        break
                    else:
                        chunk = logical_image[addr : addr + req_len]
                        sess.send_sysex(build_response(addr, chunk, req_len, fl))
                        served_count += 1
                        pct = (addr / len(logical_image)) * 100
                        print(f"\r  Stage 1 verify: {pct:5.1f}% (addr 0x{addr:06X})", end="", flush=True)

            if time.time() - last_req_time > 8.0:
                if served_count > 0:
                    print("\n  Device transitioning to bootloader mode...")
                break

    finally:
        sess.close()

    if stage2_done:
        print("\n[COMPLETE] Update finished successfully!")
        return

    # Stage 2: Bootloader Transfer
    print("\n--- STAGE 2: Reconnecting to OTA Bootloader ---")
    print("Waiting 3 seconds for USB re-enumeration...")
    time.sleep(3.0)

    (in_id, in_name), (out_id, out_name) = wait_for_device(timeout=15.0)
    if in_id is None or out_id is None:
        print("Error: Device did not re-appear after reboot! Check USB connection.")
        sys.exit(1)

    print(f"Reconnected to In:[{in_id}] {in_name} / Out:[{out_id}] {out_name}...")
    sess2 = WinMidiSession(in_id, out_id)

    try:
        sess2.send_sysex(HS_QUERY)
        resp2 = sess2.recv_sysex(timeout=2.0)
        if resp2:
            ident2 = parse_handshake_identity(resp2)
            print(f"  Bootloader identity: {ident2}")

        print("  Starting firmware transfer...")
        sess2.send_sysex(UPGRADE_CMD)
        time.sleep(0.5)

        last_req_time = time.time()
        transferred = 0

        while True:
            pkt = sess2.recv_sysex(timeout=0.1)
            if pkt:
                req = parse_request(pkt)
                if req:
                    fl, addr, req_len = req
                    last_req_time = time.time()

                    if addr == 0xF0000000:
                        print("\n\n[SUCCESS] Flash complete! Finalizing write and rebooting...")
                        sess2.send_sysex(build_success(addr))
                        stage2_done = True
                        break
                    elif addr == 0xE0000000:
                        sess2.send_sysex(build_success(addr))
                    else:
                        chunk = logical_image[addr : addr + req_len]
                        time.sleep(0.004) # Pacing for Flash write cycle
                        sess2.send_sysex(build_response(addr, chunk, req_len, fl))
                        transferred += len(chunk)
                        pct = (addr / len(logical_image)) * 100
                        print(f"\r  Writing Flash: {pct:5.1f}% ({addr} / {len(logical_image)} bytes)", end="", flush=True)

            if time.time() - last_req_time > REQ_TIMEOUT:
                if transferred > 0:
                    print("\n[TIMEOUT] Transfer timeout during Stage 2.")
                break

    finally:
        sess2.close()

    if stage2_done:
        print("\nWaiting for device to boot into updated firmware...")
        time.sleep(4.0)
        (in_id, in_name), (out_id, out_name) = wait_for_device(timeout=10.0)
        if in_id is not None and out_id is not None:
            try:
                chk = WinMidiSession(in_id, out_id)
                chk.send_sysex(HS_QUERY)
                final_resp = chk.recv_sysex(timeout=2.0)
                chk.close()
                if final_resp:
                    final_id = parse_handshake_identity(final_resp)
                    print(f"[VERIFIED] Active firmware version: {final_id}")
            except Exception:
                pass
        print("\n[COMPLETE] Update finished successfully!")
    else:
        print("\n[INFO] If the keyboard is still flashing, wait for the screen to reboot.")


def main():
    parser = argparse.ArgumentParser(description="M-VAVE SMK-37 Pro Windows USB-MIDI OTA Flasher")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("scan", help="Scan Windows MIDI devices and query identity")

    flash_parser = sub.add_parser("flash", help="Flash .fwsc firmware file to SMK-37 Pro")
    flash_parser.add_argument("fwsc", type=Path, help="Path to .fwsc file")
    flash_parser.add_argument("--in-port", type=int, default=None, help="Override MIDI Input port index")
    flash_parser.add_argument("--out-port", type=int, default=None, help="Override MIDI Output port index")

    args = parser.parse_args()
    if args.cmd == "scan":
        cmd_scan()
    elif args.cmd == "flash":
        cmd_flash(args.fwsc, in_override=args.in_port, out_override=args.out_port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
