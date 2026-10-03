# Woovebox 3.0 BLE-MIDI Connection & Pairing Guide

This guide details how to pair the **M-VAVE SMK-37 Pro** keyboard controller with the **Woovebox 3.0** synthesizer/groovebox using custom firmware **v022**.

---

## 1. Understanding the Woovebox BLE Host Architecture

The Woovebox 3.0 (powered by an ESP32-WROVER-E) operates as a BLE Central host when booted in `hoSt bLE` mode:
- **Scan & Discovery:** It continuously scans on channels 37, 38, and 39 looking for BLE-MIDI peripherals.
- **Security & Bonding:** The ESP32's Bluedroid/NimBLE stack attempts to establish link encryption using unauthenticated *Just Works* pairing and stores the Long Term Key (LTK) in its NVS flash memory.
- **GATT Routing:** Upon link completion, it discovers the standard Apple BLE-MIDI service (`03B80E5A-EDE8-4B33-A751-6CE34EC4C700`), enables notifications on characteristic `7772E5DB-3868-4112-A1A9-F2669D106BF3`, and routes incoming note packets to the currently selected Woovebox track.

---

## 2. Why Stock Firmware Failed (and How v022 Fixes It)

1. **Secondary Advertising Loops:** Stock firmware launched secondary advertising bursts when the Woovebox subscribed to notifications. v022 nops this out (Patch 1 at `0x0013D2`), ensuring clean single-link operation.
2. **Supervision Timeout Drops:** Stock firmware set a 1,000 ms timeout. v022 increases this to 4,000 ms (Patch 2 at `0x05839E`), tolerating ESP32 scheduling delays.
3. **SMP Security Rejection:** Stock firmware requested MITM and PIN display (`123456`). v022 configures `auth_req = 0x01` and `IO_CAP = 3` (NoInputNoOutput) with BLE 4.0 Legacy Pairing support (Patch 3 at `0x087446`, `0x08758A`, `0x0875C4`).
4. **Silent Notification Suppression:** Stock firmware dropped MIDI packets if the host didn't re-write the CCCD 0x2902 descriptor upon reconnecting. v022 transmits notifications unconditionally (Patch 4 at `0x000AEE`).
5. **Stale Bond Record Purge:** v022 generates a clean, unique MAC address from VM key 108 (Patch 5 at `0x0035CE`, `0x003668`), bypassing any corrupted host bond caches.

---

## 3. Step-by-Step Pairing Instructions

### Step 1: Flash Firmware v022
Ensure your SMK-37 Pro has been updated to firmware **v022**:
```bash
python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc
```

### Step 2: Turn on the Keyboard & Enable Bluetooth
1. Turn on the SMK-37 Pro using its power switch.
2. Ensure the **Wireless / BT** button is active (the blue "bt" LED blinks, waiting for a connection).

### Step 3: Boot Woovebox in BLE Host Mode
1. Power on the Woovebox while holding down the **`4/Ar` (Arp)** key.
2. The Woovebox 4-character 16-segment display will show:
   ```text
   hoSt
   bLE
   ```
3. The Woovebox enters BLE Host scanning mode and boots to the active track (e.g. Track 4 or Track 1).

### Step 4: Verification
1. Within 2 to 5 seconds, the SMK-37 Pro's blue "bt" LED will switch from **blinking to solid blue**.
2. Press any key on the SMK-37 Pro.
3. The selected Woovebox track will play notes with near-zero latency and dynamic velocity tracking.

> [!NOTE]
> The Woovebox standalone 4-character LED display does **not** show toast text like "BLE CONNECTED". Solid illumination of the keyboard's "bt" LED and immediate audio output on key press confirms an established connection.
