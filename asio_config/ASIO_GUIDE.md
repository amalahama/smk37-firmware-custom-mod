# Guía de Configuración ASIO de Mínima Latencia para M-VAVE SMK-37 Pro

El M-VAVE SMK-37 Pro cuenta con una interfaz de audio y MIDI USB Class-Compliant integrada (AC791N SoC):
- **Audio:** 2 canales de entrada / 2 canales de salida, 44.1 kHz, 24-bit.
- **MIDI:** USB-MIDI bi-direccional de alta velocidad.
- **Generador DX7:** Los 6 operadores FM del sintetizador interno se pueden rutear directamente al audio USB.

---

## 1. Controlador ASIO Instalado en tu Sistema

En tu equipo Windows ya está instalado **ASIO4ALL v2** (`HKLM\Software\ASIO\ASIO4ALL v2`).
ASIO4ALL proporciona acceso directo por **Kernel Streaming (WDM-KS)** al hardware de audio USB de la SMK-37 Pro, saltándose el mezclador del sistema de Windows (WASAPI compartido) para eliminar latencias de software y conseguir un retardo inferior a **3 ms**.

---

## 2. Configuración Paso a Paso en tu DAW (Ableton, FL Studio, Reaper, Cubase, etc.)

1. Conecta la **SMK-37 Pro** por cable USB al PC y enciéndela.
2. Abre tu DAW o programa de audio y dirígete a **Preferencias de Audio** (`Audio Settings`).
3. En **Driver Type** (Tipo de controlador), selecciona:
   ```text
   ASIO
   ```
4. En **Audio Device** (Dispositivo de audio), selecciona:
   ```text
   ASIO4ALL v2
   ```
5. Pulsa en el botón **Hardware Setup / Control Panel** (Panel de Control de ASIO4ALL):
   - Activa el modo experto haciendo clic en el icono de la **llave inglesa** (esquina inferior derecha del panel).
   - En la lista de dispositivos de la izquierda, activa únicamente:
     - `SMK-37 Pro` o `USB Audio Device`
     *(Asegúrate de desactivar tarjetas integradas Realtek o HDMI para evitar contención de reloj).*
   - **ASIO Buffer Size (Tamaño de Buffer):**
     - Selecciona **64 Samples** (Latencia: ~1.45 ms).
     - Si tu CPU sufre picos con proyectos muy cargados de plugins, selecciona **128 Samples** (~2.9 ms).
   - **Latency Compensation (Compensación de Latencia):**
     - In: `0 Samples`
     - Out: `0 Samples`
   - **Hardware Buffer (Buffer por Hardware):** Marcar la casilla (acceso directo sin capas intermedias).
   - **Always Resample 44.1k <-> 48k:** Desmarcado (utilizar 44.1 kHz nativo).

---

## 3. Latencias Conseguidas

| Tamaño de Buffer (Samples) | Frecuencia de Muestreo | Latencia de Entrada | Latencia de Salida | Latencia Round-Trip Total |
| :---: | :---: | :---: | :---: | :---: |
| **64 samples** | 44.1 kHz | **1.45 ms** | **1.45 ms** | **~2.9 ms** |
| **128 samples** | 44.1 kHz | **2.90 ms** | **2.90 ms** | **~5.8 ms** |
| **256 samples** | 44.1 kHz | **5.80 ms** | **5.80 ms** | **~11.6 ms** |

---

## 4. Opciones Alternativas: FlexASIO

Si prefieres usar **FlexASIO** (basado en WASAPI Exclusive), el instalador oficial ya ha sido descargado en:
`downloads/FlexASIO-1.10b.exe`.
Al ejecutarlo, puedes colocar el archivo de configuración `FlexASIO.toml` en tu carpeta de usuario (`C:\Users\amala\FlexASIO.toml`) con el siguiente contenido:

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
