# M-VAVE SMK-37 Pro Dedicated ASIO Driver

Driver ASIO dedicado de ultra-baja latencia y alto rendimiento desarrollado a medida para el controlador/sintetizador **M-VAVE SMK-37 Pro** en sistemas Windows 10 y Windows 11 (64-bit).

---

## 🚀 ¿Por qué este driver en lugar de ASIO4ALL?

ASIO4ALL es un wrapper genérico antiguo que suele causar graves problemas en producción musical:
1. **Bloqueo exclusivo destructivo**: ASIO4ALL bloquea el dispositivo de audio de Windows impidiendo que el navegador, YouTube o Spotify suenen simultáneamente.
2. **Inestabilidad y cuelgues**: Con cambios de frecuencia de muestreo o desconexiones del cable USB, ASIO4ALL puede provocar congelaciones o pantallazos azules (BSOD).
3. **Interfaz obsoleta y compleja**: La ventana de configuración WDM de ASIO4ALL es confusa.

**El driver dedicado M-VAVE SMK-37 Pro ASIO soluciona esto:**
- **Acceso directo WASAPI Exclusive**: Se comunica directamente con los endpoints Isochronous de audio del chip AC791N del SMK-37 Pro (24-bit PCM, 44.1 kHz, 2 In / 2 Out).
- **Latencia mínima real**: Búferes desde 32 samples (0.73 ms) y 64 samples (1.45 ms).
- **Prioridad Pro Audio MMCSS en tiempo real**: Hilo de streaming con `AvSetMmThreadCharacteristicsW("Pro Audio")` y prioridad `THREAD_PRIORITY_TIME_CRITICAL` para evitar *underruns* o *glitches*.
- **Panel de Control Integrado**: Accesible directamente desde el botón "Control Panel" de tu DAW (Ableton, FL Studio, Reaper, Cubase) o como aplicación independiente (`SMK37Pro_ControlPanel.exe`).
- **Autónomo y ultra-ligero**: 100% estático, sin dependencias de DLLs externas ni instaladores pesados de terceros.

---

## 📊 Tabla de Latencias (44.1 kHz)

| Tamaño de Búfer (Samples) | Latencia Unidireccional | Latencia Roundtrip (Aprox.) | Uso Recomendado |
|:---:|:---:|:---:|:---|
| **32** | **0.73 ms** | **~ 1.8 ms** | Rendimiento extremo / Monitoreo ultra-rápido |
| **64** *(Por defecto)* | **1.45 ms** | **~ 2.9 ms** | **Tocar en vivo y grabación de sintetizador** |
| **128** | **2.90 ms** | **~ 5.8 ms** | Proyectos medianos con muchos plugins VST |
| **256** | **5.80 ms** | **~ 11.6 ms** | Producción general y mezcla con alta carga de CPU |
| **512** | **11.61 ms** | **~ 23.2 ms** | Mezcla y masterización pesada |
| **1024** | **23.22 ms** | **~ 46.4 ms** | Proyectos masivos con búfer relajado |

---

## 🎧 Asignación de Canales de Audio

El SMK-37 Pro integra tanto un controlador MIDI como una interfaz de audio USB y un motor de síntesis FM (DX7):

- **Entradas ASIO (Inputs 1 & 2)**:
  - `SMK-37 In L (DX7)`
  - `SMK-37 In R (DX7)`
  - *Permite grabar directamente el audio generado por el sintetizador interno del SMK-37 Pro en tu DAW sin cables adicionales.*
- **Salidas ASIO (Outputs 1 & 2)**:
  - `SMK-37 Out L`
  - `SMK-37 Out R`
  - *Envía la salida de audio de tu DAW directamente a la salida de auriculares/jack de 3.5mm del SMK-37 Pro con mínima latencia.*

---

## 🛠️ Instalación Rápida

1. Conecta tu **M-VAVE SMK-37 Pro** mediante cable USB al ordenador.
2. Abre la carpeta `driver_asio` y haz doble clic en:
   ```cmd
   install_driver.bat
   ```
3. El driver se registrará automáticamente en el Registro de Windows bajo `M-VAVE SMK-37 Pro ASIO` (GUID `{7C38B80E-5AED-4B33-A751-6CE34EC4C701}`).

---

## 🎹 Configuración en tu DAW

### 1. Ableton Live
1. Ve a **Options > Preferences > Audio**.
2. **Driver Type**: Selecciona `ASIO`.
3. **Audio Device**: Selecciona `M-VAVE SMK-37 Pro ASIO`.
4. Haz clic en **Hardware Setup** para abrir el Panel de Control y cambiar el búfer si lo deseas.

### 2. FL Studio
1. Ve a **Options > Audio Settings**.
2. En la sección **Input / Output**, selecciona en el desplegable de dispositivos ASIO: `M-VAVE SMK-37 Pro ASIO`.
3. Haz clic en **Show ASIO Panel** para configurar búfer o modo exclusivo.

### 3. REAPER
1. Ve a **Options > Preferences > Audio > Device**.
2. **Audio system**: Selecciona `ASIO`.
3. **ASIO Driver**: Selecciona `M-VAVE SMK-37 Pro ASIO`.
4. Habilita las entradas y salidas (1 a 2).
5. Haz clic en **ASIO Configuration...** para ver el panel.

### 4. Cubase / Nuendo / Studio One
1. Ve a la configuración de audio (**Studio Setup > Audio System** o **Audio Device**).
2. Selecciona `M-VAVE SMK-37 Pro ASIO` como controlador ASIO maestro.
3. Haz clic en **Control Panel** para ajustar la latencia.

---

## 🎛️ Panel de Control Independiente

Puedes abrir el panel de configuración sin abrir ningún DAW ejecutando:
```cmd
driver_asio\bin\SMK37Pro_ControlPanel.exe
```
Permite:
- Ver el dispositivo endpoint detectado en tiempo real.
- Seleccionar el tamaño de búfer (32 a 1024 samples) viendo la latencia calculada exacta en milisegundos.
- Activar/desactivar el modo WASAPI Exclusive.
- Notificación dinámica de reinicio de búfer (`kAsioResetRequest`) a DAWs activos sin necesidad de reiniciarlos.

---

## 🧪 Pruebas Automatizadas de Verificación

El proyecto incluye un test automatizado en Python (`test_asio_driver.py`) que simula el ciclo de vida completo de un DAW profesional:
```cmd
python test_asio_driver.py
```
**Pruebas que realiza:**
- Instanciación COM Class Factory de `CLSID_SMK37Pro_ASIO`.
- Verificación del VTable de Steinberg `IASIO`.
- Consulta de canales (2 in / 2 out) e información de canales.
- Asignación de doble búfer (Ping-Pong buffers de 32-bit).
- Streaming de audio en tiempo real y recepción de callbacks `bufferSwitch`.
- Seguimiento de posición de muestras (`samplePosition`).
- Detención y liberación limpia de recursos.

---

## 🗑️ Desinstalación

Para desregistrar el driver del sistema:
```cmd
uninstall_driver.bat
```
