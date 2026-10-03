# M-VAVE SMK-37 Pro Custom Firmware v022

## English

### What's New in v022
- **Woovebox 3.0 BLE-MIDI Host Mode Fix:** Complete solution for Bluetooth pairing with Woovebox (`hoSt bLE` / `4/Ar`). Notes transmit instantly without lag or dropped packets.
- **Unconditional BLE-MIDI Notifications:** Eliminates silent suppression of MIDI note packets on reconnection (bypasses CCCD gate).
- **Security Manager Just Works Bonding:** Replaces buggy MITM / Passkey requirements with standard Just Works bonding (`auth_req = 0x01`, `IO_CAP = 3`, Legacy Pairing 4.0/4.2 compatible).
- **Secondary Advertising Suppression:** Prevents RF channel collisions (37/38/39) during active BLE connections.
- **Connection Parameters Relaxation:** Increased supervision timeout from 1,000 ms to 4,000 ms to tolerate embedded host timing jitter.
- **Fresh Unique MAC Address:** Bypasses stale bond caches on host devices.
- **M-VAVE Mobile App & USB MIDI:** 100% backward compatible.

### How to Flash (Windows)

#### Option A: Quick One-Click Flasher
1. Connect your **M-VAVE SMK-37 Pro** keyboard to your PC using a USB cable.
2. Ensure any DAWs (Ableton, FL Studio, Reaper), MIDI monitors, or CubeSuite apps are closed.
3. Double-click `flash_v022.bat` and follow the on-screen prompts.

#### Option B: Manual Command Line
Requires Python 3.7+ (uses standard library `ctypes` and `winmm.dll`, zero external packages required):
```bash
# 1. Verify device detection
python smk_ota_win.py scan

# 2. Flash firmware
python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc
```

---

## Español

### Novedades en v022
- **Compatibilidad con Woovebox 3.0 BLE-MIDI:** Solución completa para el modo host de Woovebox (`hoSt bLE` / `4/Ar`). Transmisión inmediata de notas con latencia mínima y sin notas colgadas.
- **Notificaciones BLE-MIDI Incondicionales:** Evita que el firmware silencie los paquetes de notas MIDI al reconectar si el host no reescribe el descriptor CCCD 0x2902.
- **Emparejamiento Just Works con Bonding:** Reemplaza la petición de PIN/MITM por Just Works (`auth_req = 0x01`, `IO_CAP = 3`, compatible con BLE 4.0/4.2).
- **Supresión de Anuncio Secundario:** Evita ráfagas de publicidad BLE concurrentes en canales 37/38/39 durante una conexión activa.
- **Supervision Timeout de 4,000 ms:** Previene micro-desconexiones por fluctuaciones de radiofrecuencia en el ESP32.
- **Regeneración de Dirección MAC Limpia:** Elude registros de emparejamiento corruptos o desactualizados en hosts externos.
- **Compatibilidad Total:** Mantiene compatibilidad con USB MIDI, DAWs y la app móvil oficial M-VAVE.

### Cómo Flashear (Windows)

#### Opción A: Flasheador con un Clic
1. Conecta el teclado **M-VAVE SMK-37 Pro** al ordenador mediante cable USB.
2. Cierra cualquier DAW (Ableton, FL Studio, etc.), monitor MIDI o la app CubeSuite.
3. Haz doble clic en `flash_v022.bat` y sigue las instrucciones en pantalla.

#### Opción B: Línea de Comandos
Solo necesitas Python 3.7+ (utiliza la librería estándar de Windows vía `winmm.dll`, sin dependencias externas):
```bash
# 1. Comprobar detección del teclado
python smk_ota_win.py scan

# 2. Flashear firmware v022
python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc
```
