# M-VAVE SMK-37 Pro Custom Firmware v022

## Overview
Custom firmware update for the **M-VAVE SMK-37 Pro** keyboard controller, specifically engineered for zero-lag, continuous Bluetooth Low Energy (BLE) MIDI connectivity with embedded host synthesizers (especially **Woovebox 3.0** in `hoSt bLE` mode) and rock-solid USB-MIDI DAW performance.

---

## What's New in v022
- **Woovebox 3.0 BLE-MIDI Host Mode Support:** Direct, automatic pairing with Woovebox in `hoSt bLE` (`4/Ar` Arp track). Notes transmit in real time with near-zero latency.
- **Unconditional BLE-MIDI Notifications:** Eliminates silent suppression of MIDI note packets upon reconnection (bypasses the CCCD check gateway).
- **Security Manager Just Works Bonding:** Replaces buggy MITM / Passkey requirements with standard Just Works bonding (`auth_req = 0x01`, `IO_CAP = 3`, 100% BLE 4.0/4.2 compatible).
- **Secondary Advertising Suppression:** Prevents concurrent advertising bursts across RF channels 37/38/39 while a connection is active, avoiding scanner collisions and loop disconnects.
- **Connection Parameters Relaxation:** Increased supervision timeout from 1,000 ms to 4,000 ms with flexible intervals (7.5-20 ms / 15-30 ms), eliminating RF dropouts from ESP32 task scheduling jitter.
- **Clean Unique MAC Address Generation:** Redirects flash VM MAC key from 102 to 108, generating a fresh Bluetooth address to clear stale/broken host bond caches.
- **Official M-VAVE Mobile App & USB MIDI:** 100% backward compatible (proprietary descriptor intact).

---

## How to Flash (Windows)

### Option A: Quick One-Click Flasher (Recommended)
1. Connect your **M-VAVE SMK-37 Pro** keyboard to your PC using a USB cable.
2. Close all DAWs (Ableton Live, FL Studio, Reaper), MIDI monitors, and CubeSuite software.
3. Double-click `flash_v022.bat` and follow the on-screen prompts.
4. The process takes ~15 seconds. Once finished, the keyboard will reboot with firmware v022.

### Option B: Manual Command Line
Requires standard Python 3.7+ (uses built-in `ctypes` and `winmm.dll`, zero external packages required):
```bash
# 1. Scan and verify device detection
python smk_ota_win.py scan

# 2. Flash custom firmware v022
python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc
```
