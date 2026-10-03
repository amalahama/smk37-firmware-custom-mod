# M-VAVE SMK-37 Pro Custom Firmware & BLE/ASIO Mods

[![Release](https://img.shields.io/github/v/release/amalahama/smk37-firmware-custom-mod?style=flat-square)](https://github.com/amalahama/smk37-firmware-custom-mod/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Custom firmware modifications, architecture documentation, Windows flasher tool, and dedicated ASIO driver for the **M-VAVE SMK-37 Pro** MIDI controller keyboard (JieLi AC791N SoC).

---

## 🚀 Quick Start / Flashing v022

To update your SMK-37 Pro to custom firmware **v022** (resolves Woovebox 3.0 BLE-MIDI pairing/notes and DAW stability):

1. Download the latest release package: [**`SMK-37_Pro_custom_v022_flasher.zip`**](https://github.com/amalahama/smk37-firmware-custom-mod/releases/latest)
2. Extract the ZIP folder.
3. Connect your SMK-37 Pro to your PC via USB cable and close all DAWs/MIDI software.
4. Run `flash_v022.bat` (or run `python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc`).

---

## 1. Project Objectives
1. **BLE MIDI Stability with Woovebox 3.0:** Enable Woovebox 3.0 (ESP32-based hardware synthesizer in `hoSt bLE` / `4/Ar` mode) to reliably discover, pair, and maintain a rock-solid, low-latency BLE-MIDI connection with the SMK-37 Pro, transmitting notes continuously without dropouts or frozen states.
2. **Dedicated Low-Latency Windows ASIO Driver:** Optimize the SMK-37 Pro as a USB Audio Class 1.0 (UAC1) interface and MIDI controller on Windows, achieving true low latency (< 4-6 ms roundtrip) via a dedicated ASIO driver with a circular FIFO ring buffer that eliminates buffer overruns and DAW crashes (CTD).

---

## 2. Technical Diagnostics & Root Cause Analysis
* **Hardware Platform:** JieLi AC791N / WL82 SoC (Dual-Core pi32v2 CPU @ 240-320MHz).
* **Base Firmware:** Stock image `SMK-37_Pro_016.fwsc` (version 1.16).
* **JLFS Encryption:** JieLi SFC cipher with chipkey `0x980F` (38927) and header key `0xFFFF`.
* **Root Causes of Incompatibility with Woovebox 3.0 (ESP32 Host):**
  1. **Concurrent Secondary Advertising:** When the host subscribed to BLE-MIDI notifications (CCCD 0x2902), the stock firmware launched secondary advertising bursts on RF channels 37/38/39, confusing the ESP32 host scanner and causing connection loops.
  2. **Rigid Supervision Timeout:** The stock 1,000 ms supervision timeout dropped connections upon minor RF jitter or FreeRTOS task scheduling delays on the ESP32.
  3. **SMP Authentication Rejection:** The stock stack demanded MITM / Passkey Display pairing, causing headless embedded hosts without displays or keypads to time out.
  4. **CCCD Gate on Note Dispatch:** Routine `0x02000AD4` silently dropped MIDI note packets if the host didn't re-write CCCD `0x2902` upon reconnecting to an already bonded link.
  5. **NVS Stale Bond Cache Collision:** The keyboard cached its static MAC address in flash VM key 102. If the host retained a broken or incomplete security record for that address, reconnects hung indefinitely.
* **Complete Solution:** Custom Firmware **v022** surgically patches these 5 architectural flaws at the `pi32v2` machine code level while preserving 100% backward compatibility with USB MIDI, desktop DAWs, and the official M-VAVE mobile app.

---

## 3. Repository Structure
* `release/`: Flashable binaries, batch scripts, and the pre-packaged `SMK-37_Pro_custom_v022_flasher.zip`.
* `tools/`:
  - `repack_smk.py`: Automated unpacker, patcher, and SFC re-encryptor for `.fwsc` containers.
  - `unpack_smk.py`: De-interleaves 36-block extended containers and extracts JLFS/UFW components.
  - `smk_ota_win.py`: Zero-dependency Windows USB-MIDI SysEx OTA flasher.
  - `jltech/`: Self-contained JieLi encryption, CRC, and cipher package.
* `stock_firmware/`: Reference stock firmware v016 (`SMK-37_Pro_016.fwsc`).
* `firmware_work/`: Verified custom firmware builds (v017 through v022).
* `BLE_EXTENDED_PATCH.txt`: Complete technical specification and assembly-level reference for all applied BLE patches.
* `driver_asio/`: Dedicated 64-bit native Windows ASIO COM driver (`SMK37Pro_ASIO.dll`), control panel GUI (`SMK37Pro_ControlPanel.exe`), automated tests, and installation scripts.
* `docs/`: In-depth firmware architecture, reverse-engineered function maps, and Woovebox setup guides.
* `PLAN.md`: Milestone progress roadmap.

---

## 4. Current Development Status

### ✅ Custom Firmware v022 (Verified & Fully Functional with Woovebox 3.0)
- **Production Binary:** `firmware_work/SMK-37_Pro_custom_022.fwsc` (SHA-256: `fe51c1c6eba90dc9aabe40900457aa1c1ddb3d9c32391335b1aceaded1d2035f`).
- **Surgical Assembly Patches Applied:**
  1. **Secondary Advertising Suppression (Offset `0x0013D2`):** Unconditional jump bypassing multi-slot advertising triggers during active connections.
  2. **Connection Parameters Relaxation (Offset `0x05839E`):** Increased supervision timeout to 4,000 ms with flexible intervals (7.5-20 ms / 15-30 ms).
  3. **SMP "Just Works" Bonding (Offsets `0x087446`, `0x08758A`, `0x0875C4`):** Configured `auth_req = 0x01` (Bonding without MITM), `IO_CAP = 3` (NoInputNoOutput), and removed mandatory Secure Connections for full BLE 4.0/4.2 compatibility.
  4. **Unconditional BLE-MIDI Notifications (Offset `0x000AEE`):** NOPs the CCCD check, guaranteeing MIDI note packets are transmitted even if the host Central skips re-writing descriptor 0x2902.
  5. **Clean Unique MAC Generation (Offsets `0x0035CE`, `0x003668`):** Redirects Flash VM MAC key from 102 to 108, generating a fresh Bluetooth address to clear stale host bond records.
  6. **Version Bump to v022 & Checksum Integrity:** Recalculated all JLFS/UFW CRC16s, re-encrypted with SFC chipkey `0x980F`, and updated container trailer markers.
- **Full Architecture Guide:** [`BLE_EXTENDED_PATCH.txt`](BLE_EXTENDED_PATCH.txt).

### ✅ USB MIDI Subsystem & DAW Integration (Verified)
- **Direct WinMM Verification:** Dynamic velocity response (25-93) verified across all 37 keys with clean Note On (`0x90`) and Note Off (`0x80`) on Channel 1 without stuck notes or dropped packets.
- **DAW Compatibility:** Verified with Ableton Live, Reaper, FL Studio, and Logic Pro.

### ✅ Dedicated Ultra-Low Latency ASIO Driver (`driver_asio`)
- **Architecture:** User-mode COM InProc server (`SMK37Pro_ASIO.dll`, CLSID `{7C38B80E-5AED-4B33-A751-6CE34EC4C701}`).
- **Circular FIFO Ring Buffer:** Prevents buffer underruns and DAW crashes (CTD), ensuring pristine, continuous audio playback.
- **WASAPI Exclusive Engine:** Direct communication with USB Audio Class 1.0 endpoints (2-in / 2-out, 24-bit PCM, 44.1 kHz), bypassing the Windows audio engine.
- **Ultra-Low Latency:** Configurable buffer sizes from 32 samples (0.73 ms) to 2048 samples (46.4 ms).
- **Real-Time MMCSS Thread:** MMCSS *"Pro Audio"* scheduling with ping-pong double buffering.
- **Control Panel:** Native Win32 GUI accessible directly via DAW *Hardware Setup* / *Control Panel* buttons or as a standalone executable (`bin/SMK37Pro_ControlPanel.exe`).
