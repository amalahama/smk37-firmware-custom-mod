# Guía de Conexión BLE-MIDI con Woovebox 3.0

Esta guía explica el problema que impedía la conexión BLE entre el **M-VAVE SMK-37 Pro** y el **Woovebox 3.0**, la solución aplicada en el firmware personalizado **V017**, y los pasos para emparejarlos.

---

## 1. Causa Raíz Descubierta en el Firmware de Fábrica (V11 a V16)

El Woovebox 3.0 (basado en ESP32-WROVER-E) en modo host (`hoSt bLE`) escanea el espectro Bluetooth Low Energy buscando dispositivos que anuncien en su paquete principal (`ADV_IND`) el identificador estándar de servicio **BLE-MIDI de la MIDI Association**:
```text
UUID: 03B80E5A-EDE8-4B33-A751-6CE34EC4C700
En formato little-endian: 00 C7 C4 4E E3 6C 51 A7 33 4B E8 ED 5A 0E B8 03
```

### El Fallo en el Código Original de M-VAVE:
En la rutina de ensamblado del paquete de publicidad (`bt_ble_adv_enable` en el offset `0x00075E` de `app.bin`):
- **Código original:**
  ```assembly
  75e: 05 f1 95 26    r5 = r2 + 1685   # b[r3+4] = r5 (tipo 0x07)
  764: 10 8f          rep 4 16 { r7 = b[r5++=1]; b[r1++=1] = r7 }
  ```
- **Consecuencia:**
  El cálculo `r2 + 1685` apuntaba a una tabla de datos genéricos en `0x0584AE` (`01 00 00 00 02 03 03...`) en vez de apuntar a la dirección real del UUID BLE-MIDI (`0x05838E`).
- Por culpa de este error de puntero, el teclado transmitía un **UUID falso/basura** en el aire. El Woovebox filtraba los anuncios entrantes y **descartaba por completo el SMK-37 Pro**, haciendo imposible el emparejamiento.

---

## 2. El Parche Quirúrgico en V017 (`SMK-37_Pro_custom_017.fwsc`)

Se ha corregido el cálculo de desplazamiento para redirigir el puntero exactamente al UUID 128-bit de BLE-MIDI:
- **Código parcheado:**
  ```assembly
  75e: 05 f1 75 25    r5 = r2 + 1397   # b[r3+4] = r5
  ```
- **Resultado:**
  El paquete de publicidad emitido por la SMK-37 Pro ahora contiene:
  1. **Flags:** `02 01 06` (Modo general detectable, BR/EDR no soportado).
  2. **128-bit Service UUID:** `11 07 00 C7 C4 4E E3 6C 51 A7 33 4B E8 ED 5A 0E B8 03` (Estándar BLE-MIDI oficial).
  3. **Datos de Fabricante:** `06 FF 00 53 74 65 70`.
  4. **Scan Response:** Nombre completo `"SMK-37 Pro"`.

---

## 3. Parámetros de Conexión BLE y Latencia

El firmware tiene preconfigurados en `0x5839E` los siguientes parámetros de negociación:
- **Intervalo Mínimo:** 6 (7.5 ms).
- **Intervalo Máximo:** 9 (11.25 ms).
- **Latencia:** 0 (respuesta inmediata en cada evento de conexión).
- **Supervision Timeout:** 100 (1000 ms).

Estos valores cumplen al 100% con la especificación recomendada por Apple y la MIDI Association para comunicación BLE-MIDI de tiempo real.

---

## 4. Instrucciones de Emparejamiento con Woovebox 3.0

1. **Flashear el firmware V017:**
   Sigue las instrucciones de flasheo ejecutando en el PC:
   ```powershell
   & .venv\Scripts\python.exe tools\smk_ota_win.py flash firmware_work\SMK-37_Pro_custom_017.fwsc
   ```
2. **Encender el SMK-37 Pro:**
   - Asegúrate de que el indicador Bluetooth (icono BLE en la pantalla LCD) esté parpadeando (modo anuncio/broadcasting activo).
3. **Poner el Woovebox en modo Host BLE:**
   - En tu Woovebox, navega al menú del sistema (**SYS** / Glob).
   - Ve a la página **bLE**.
   - Gira el encoder hasta seleccionar **hoSt** (Host BLE).
   - Pulsa el botón **Play** (o confirma con el botón de selección) para iniciar el escaneo.
4. **Emparejamiento Automático:**
   - El Woovebox detectará inmediatamente el servicio BLE-MIDI del SMK-37 Pro.
   - En la pantalla del Woovebox aparecerá la confirmación de conexión (`Conn` / nombre del dispositivo).
   - El icono Bluetooth en el SMK-37 Pro pasará de parpadear a estar **fijo**.
5. **Listo para tocar:**
   - Todas las 37 teclas, pads de velocidad, aftertouch, encoders, faders y ruedas de pitch/modulación enviarán eventos MIDI directamente al sintetizador y sampler del Woovebox con latencia ultra-baja.
