# M-VAVE SMK-37 Pro Custom Firmware & BLE/ASIO Mods

[![Release](https://img.shields.io/github/v/release/amalahama/smk37-firmware-custom-mod?style=flat-square)](https://github.com/amalahama/smk37-firmware-custom-mod/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Custom firmware modifications, architecture documentation, Windows flasher tool, and dedicated ASIO driver for the **M-VAVE SMK-37 Pro** MIDI controller keyboard (JieLi AC791N SoC).

---

## 🚀 Quick Start / Flashing v022

To update your SMK-37 Pro to custom firmware **v022** (resolves Woovebox 3.0 BLE-MIDI pairing/notes and DAWs stability):

1. Download the latest release package: [**`SMK-37_Pro_custom_v022_flasher.zip`**](https://github.com/amalahama/smk37-firmware-custom-mod/releases/latest)
2. Extract the ZIP folder.
3. Connect your SMK-37 Pro to your PC via USB and close all DAWs/MIDI software.
4. Run `flash_v022.bat` (or run `python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc`).

---

## 1. Objetivos del Proyecto
1. **Estabilidad BLE MIDI con Woovebox 3.0:** Lograr que la Woovebox (basada en ESP32 en modo `hoSt bLE` / `4/Ar`) descubra, empareje y mantenga una conexión BLE MIDI estable y de baja latencia con el SMK-37 Pro, transmitiendo notas continuamente sin caídas.
2. **Drivers ASIO / Baja Latencia en Windows:** Optimizar el funcionamiento del SMK-37 Pro como interfaz de audio USB (UAC1) y controlador MIDI, reduciendo la latencia (< 4-6 ms) en Windows mediante un driver ASIO dedicado con buffer circular FIFO anti-CTD.

---

## 2. Diagnóstico Técnico y Causas Raíz
* **Plataforma Hardware:** SoC JieLi AC791N / WL82 (CPU Dual-Core pi32v2 @ 240-320MHz).
* **Firmware Base:** Imagen de fábrica `SMK-37_Pro_016.fwsc` (versión 1.16).
* **Cifrado JLFS:** SFC Cipher con clave de chip `0x980F` (38927) y cabecera `0xFFFF`.
* **Causas Raíz de Incompatibilidad con Woovebox 3.0 (ESP32):**
  1. **Anuncio Secundario Concurrente:** Al suscribirse a notificaciones BLE-MIDI, el firmware lanzaba una segunda ráfaga de publicidad en canales 37/38/39 que confundía al escáner continuo del host ESP32.
  2. **Supervision Timeout Rígido:** El timeout de 1,000 ms provocaba micro-desconexiones con la menor fluctuación de RF en el ESP32.
  3. **Rechazo SMP:** El stack solicitaba autenticación MITM / Display cuando los hosts embebidos requieren Just Works sin PIN.
  4. **Comprobación de CCCD en Transmisión:** El manejador de notas (`0x02000AD4`) silenciaba las notas si el host no reescribía el descriptor 0x2902 tras reconectar.
  5. **Caché de Enlace NVS:** La dirección MAC almacenada en la clave VM 102 quedaba bloqueada si el host guardaba un enlace previo fallido.
* **Solución Integral:** Firmware **v022** resuelve quirúrgicamente estos 5 problemas en código máquina pi32v2 preservando 100% de compatibilidad con la app M-VAVE y DAWs por USB.


---

## 3. Estructura del Repositorio
* `driver_asio/`: Driver ASIO nativo de 64-bit para Windows (`SMK37Pro_ASIO.dll`), panel de control (`SMK37Pro_ControlPanel.exe`), motor con buffer circular FIFO y tests.
* `firmware_work/`: Firmware custom modificado (`SMK-37_Pro_custom_022.fwsc`) verificado y funcional con Woovebox 3.0 BLE y DAWs.
* `tools/`: Herramientas de empaquetado/desempaquetado (`repack_smk.py`), flasher OTA por SysEx USB-MIDI (`smk_ota_win.py`), pruebas MIDI (`test_midi.py`).
* `BLE_EXTENDED_PATCH.txt`: Especificación técnica detallada y guía de arquitectura de todos los parches aplicados al stack BLE.
* `smk-37-pro-docs/`: Volcados oficiales de firmware (V11 a V16), manuales, esquemas e ingeniería inversa de hardware.
* `FM-1-RE/`: Desensamblador, bases de datos de funciones de la CPU pi32v2, scripts de extracción y cliente OTA para flasheo por USB.
* `docs/`: Documentación técnica y bitácoras de pruebas.
* `PLAN.md`: Hoja de ruta paso a paso.

---

## 4. Estado Actual del Desarrollo

### ✅ Firmware Custom V022 (Validado y Funcional al 100% con Woovebox 3.0 BLE-MIDI)
- **Imagen de Producción:** `firmware_work/SMK-37_Pro_custom_022.fwsc` (SHA-256: `fe51c1c6eba90dc9aabe40900457aa1c1ddb3d9c32391335b1aceaded1d2035f`).
- **Parches Quirúrgicos Implementados:**
  1. **Supresión de Anuncio Secundario (Offset `0x0013D2`):** Salto incondicional que evita la ráfaga de anuncios concurrentes en canales 37/38/39 al suscribirse a notificaciones BLE-MIDI, previniendo bucles de reconexión y colisiones de RF.
  2. **Relajación de Parámetros de Conexión (Offset `0x05839E`):** Aumento del supervision timeout de 1,000 ms a 4,000 ms con intervalos flexibles (7.5-20 ms / 15-30 ms), tolerando el jitter del ESP32.
  3. **Seguridad SMP "Just Works" con Bonding (Offsets `0x087446`, `0x08758A`, `0x0875C4`):** Configurado `auth_req = 0x01` (Bonding sin MITM), `IO_CAP = 3` (NoInputNoOutput) y eliminación de Secure Connections obligatorias para compatibilidad plena BLE 4.0/4.2.
  4. **Transmisión Incondicional de Notificaciones (Offset `0x000AEE`):** NOP en la comprobación de CCCD en `ble_midi_tx_packet_dispatch`, garantizando que las notas se envían aunque el host no reescriba el descriptor 0x2902 al reconectar.
  5. **Regeneración de Dirección MAC Limpia (Offsets `0x0035CE`, `0x003668`):** Redirección de la clave VM flash de 102 a 108, forzando la generación de una nueva MAC única que elude cachés de enlace corruptos o incompletos en hosts externos como Woovebox.
  6. **Bump de Versión a v022 y Recalculación CRC/SFC:** Verificación integral de todos los bloques JLFS y cabecera UFW.
- **Documento de Referencia Técnica:** [`BLE_EXTENDED_PATCH.txt`](file:///O:/PROGRAMACION/GEMINI%20ANTIGRAVITY/SMK37mod/BLE_EXTENDED_PATCH.txt).

### ✅ Subsistema USB MIDI y DAWs (Validado)
- **Captura Directa WinMM:** Verificada respuesta dinámica de los 37 sensores de velocidad (25-93) y transmisión limpia de Note On (`0x90`) / Note Off (`0x80`) en canal 1 sin notas pegadas ni pérdida de paquetes.
- **Compatibilidad DAW (Ableton Live / Reaper / Logic):** Configuración documentada sin conflictos de scripts de superficies de control.

### ✅ Driver ASIO Nativo de Ultra-Baja Latencia (`driver_asio`)
- **Arquitectura:** Driver COM nativo en modo usuario (`SMK37Pro_ASIO.dll`, CLSID `{7C38B80E-5AED-4B33-A751-6CE34EC4C701}`).
- **Buffer Circular FIFO:** Previene desbordamientos y caídas (CTD) en DAWs, garantizando streaming de audio cristalino y continuo.
- **Motor WASAPI Exclusive:** Conexión directa a los endpoints USB Audio Class 1.0 (2-in / 2-out, 24-bit PCM, 44.1 kHz), puenteando el mezclador de Windows.
- **Ultra-Baja Latencia:** Búferes desde 32 samples (0.73 ms) y 64 samples (1.45 ms unidireccional / < 3 ms roundtrip).
- **Hilo en Tiempo Real:** Prioridad MMCSS *"Pro Audio"* con doble búfer ping-pong.
- **Panel de Control:** GUI nativa Win32 integrada en el botón "Control Panel" de los DAWs y como ejecutable standalone (`bin/SMK37Pro_ControlPanel.exe`).
- **Pruebas Superadas:** Test automatizado `test_asio_driver.py` con ciclo de vida completo en DAW aprobado al 100%.

