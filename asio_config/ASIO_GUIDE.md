# Low-Latency Audio Configuration Guide for M-VAVE SMK-37 Pro

The M-VAVE SMK-37 Pro features an integrated USB Class-Compliant audio and MIDI interface (JieLi AC791N SoC):
- **Audio:** 2 input channels / 2 output channels, 44.1 kHz, 24-bit PCM.
- **MIDI:** High-speed bidirectional USB-MIDI.
- **DX7 FM Synth Engine:** The 6 operators of the internal FM engine can be routed directly to USB audio.

---

## 1. Native SMK-37 Pro Dedicated ASIO Driver (Recommended)

Our repository provides a dedicated, native 64-bit ASIO driver (`driver_asio/bin/SMK37Pro_ASIO.dll`):
- Direct WASAPI Exclusive / Shared access with circular FIFO ring buffer.
- Buffer sizes from 32 samples (0.73 ms) to 2048 samples (46.4 ms).
- Standalone Win32 control panel (`SMK37Pro_ControlPanel.exe`).
- Zero dependencies on third-party wrappers.

---

## 2. Alternative Configuration via ASIO4ALL v2

If using ASIO4ALL v2 (`HKLM\Software\ASIO\ASIO4ALL v2`):
1. Connect the **SMK-37 Pro** via USB cable and power it on.
2. In your DAW, open **Audio Settings** and select **ASIO** -> **ASIO4ALL v2**.
3. Open **Hardware Setup / Control Panel**:
   - Enable advanced/expert mode (wrench icon).
   - In the device list on the left, activate only: `SMK-37 Pro` / `USB Audio Device`.
   - Set **ASIO Buffer Size** to `64 Samples` (~1.45 ms) or `128 Samples` (~2.9 ms).
   - Uncheck "Always Resample 44.1k <-> 48k" to maintain native 44.1 kHz.

---

## 3. Measured Latencies (44.1 kHz)

| Buffer Size (Samples) | Sample Rate | Input Latency | Output Latency | Total Round-Trip Latency |
| :---:| :---:| :---:| :---:| :---:|
| **64 samples** | 44.1 kHz | **1.45 ms** | **1.45 ms** | **~2.9 ms** |
| **128 samples** | 44.1 kHz | **2.90 ms** | **2.90 ms** | **~5.8 ms** |
| **256 samples** | 44.1 kHz | **5.80 ms** | **5.80 ms** | **~11.6 ms** |

---

## 4. Alternative: FlexASIO Configuration

If using **FlexASIO** (WASAPI Exclusive backend), create `FlexASIO.toml` in your user home directory:

```toml
backend = "Windows WASAPI"
bufferSizeSamples = 64

[input]
device = "M-VAVE SMK-37 Pro"
wasapiExclusiveMode = true

[output]
device = "M-VAVE SMK-37 Pro"
wasapiExclusiveMode = true
```
