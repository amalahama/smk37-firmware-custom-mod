# M-VAVE SMK-37 Pro Dedicated ASIO Driver

Driver ASIO dedicado de ultra-baja latencia y alto rendimiento desarrollado a medida para el controlador/sintetizador **M-VAVE SMK-37 Pro** en sistemas Windows 10 y Windows 11 (64-bit).

---

## 🚀 ¿Por qué este driver en lugar de ASIO4ALL?

ASIO4ALL es un wrapper genérico que suele causar problemas en producción musical:
1. **Bloqueo exclusivo destructivo**: Bloquea el audio de Windows impidiendo que el navegador, YouTube o Spotify suenen mientras produces.
2. **Inestabilidad y cuelgues**: Con cambios de frecuencia de muestreo o reconexiones USB, puede congelar el DAW o provocar pantallazos azules.
3. **Desincronización MIDI**: Problemas de alineación temporal de eventos MIDI en DAWs modernos.

**El driver dedicado M-VAVE SMK-37 Pro ASIO soluciona todo esto:**
- **Acceso directo WASAPI Exclusive / Shared**: Comunicación nativa de alto rendimiento con los endpoints Isochronous de audio del chip del SMK-37 Pro (32-bit Float / 24-bit PCM, 44.1 kHz & 48.0 kHz, 2 In / 2 Out).
- **Latencia mínima real**: Búferes seleccionables en potencias de dos desde **32 samples (0.73 ms)** hasta **2048 samples (46.4 ms)**.
- **Sincronización de Reloj QPC sin deriva**: Timestamps reales en nanosegundos basados en *QueryPerformanceCounter* del sistema (`kSystemTimeValid`, `kSamplePositionValid`, `kSampleRateValid`) perfectamente alineados con los mensajes MIDI de Windows.
- **Limitador de latencia anti-deriva (Drift Clamp)**: Mantiene el búfer circular acotado y estable en sesiones de larga duración sin sobrecarga de CPU ni acumulaciones de retardo.
- **Prioridad Pro Audio MMCSS en tiempo real**: Hilo de streaming con `AvSetMmThreadCharacteristicsW("Pro Audio")` y prioridad `THREAD_PRIORITY_TIME_CRITICAL` sin operaciones de I/O en disco durante el procesamiento.
- **Panel de Control Integrado**: Accesible directamente desde tu DAW (botón *Hardware Setup* o *Control Panel*) o como aplicación independiente (`SMK37Pro_ControlPanel.exe`).
- **Autónomo y ultra-ligero**: 100% estático, sin dependencias de DLLs externas ni instaladores de terceros.

---

## 📊 Tabla de Latencias (44.1 kHz)

| Tamaño de Búfer (Samples) | Latencia Unidireccional | Latencia Roundtrip (Aprox.) | Uso Recomendado |
|:---:|:---:|:---:|:---|
| **32** | **0.73 ms** | **~ 1.8 ms** | Rendimiento extremo / Monitoreo ultra-rápido |
| **64** | **1.45 ms** | **~ 2.9 ms** | Tocar en vivo y grabación de sintetizador |
| **128** | **2.90 ms** | **~ 5.8 ms** | Proyectos medianos con sintetizadores e instrumentos |
| **256** | **5.80 ms** | **~ 11.6 ms** | Producción general y mezcla fluida |
| **512** *(Recomendado)* | **11.61 ms** | **~ 23.2 ms** | **Mezcla estándar con alta carga de plugins VST** |
| **1024** | **23.22 ms** | **~ 46.4 ms** | Proyectos masivos con orquestas o automatización pesada |
| **2048** | **46.44 ms** | **~ 92.8 ms** | Búfer relajado para masterización intensiva |

---

## 🎧 Asignación de Canales de Audio

El SMK-37 Pro integra un controlador MIDI, una interfaz de audio USB y un motor de síntesis FM (DX7):

- **Entradas ASIO (Inputs 1 & 2)**:
  - `SMK-37 In L (DX7)`
  - `SMK-37 In R (DX7)`
  - *Graba directamente el audio generado por el sintetizador interno del SMK-37 Pro en tu DAW sin cables de audio analógicos adicionales.*
- **Salidas ASIO (Outputs 1 & 2)**:
  - `SMK-37 Out L`
  - `SMK-37 Out R`
  - *Envía la salida de audio de tu DAW directamente a la salida de auriculares/jack de 3.5 mm del SMK-37 Pro con mínima latencia.*

---

## 🛠️ Instalación en 1 Clic

1. Descarga el paquete de lanzamiento (**Release**) o clona este repositorio.
2. Haz clic derecho en `install_driver.bat` y selecciona **Ejecutar como administrador**.
3. El instalador copiará los binarios a `%ProgramFiles%\M-VAVE SMK-37 Pro ASIO\` y registrará el driver en el Registro de Windows bajo `M-VAVE SMK-37 Pro ASIO` (CLSID `{7C38B80E-5AED-4B33-A751-6CE34EC4C701}`).

---

## 🎹 Configuración en tu DAW

### 1. Ableton Live

#### A. Configurar el Audio ASIO
1. Abre **Opciones > Preferencias** (`Ctrl + ,`) y ve a la pestaña **Audio**.
2. **Driver Type**: Selecciona `ASIO`.
3. **Audio Device**: Selecciona `M-VAVE SMK-37 Pro ASIO`.
4. El desplegable **Buffer Size** de Ableton te permitirá elegir directamente desde 32 hasta 2048 muestras.
5. Puedes pulsar **Hardware Setup** para abrir el Panel de Control y activar el modo *WASAPI Exclusive*.

#### B. Configurar el Teclado MIDI (¡Muy Importante!)
1. En **Preferencias**, ve a la pestaña **Link, Tempo & MIDI**.
2. En la tabla inferior de **Puertos MIDI**, localiza la fila `Input: SMK-37 Pro Midi`.
3. Activa el botón **Pista (Track)** poniéndolo en **ON** (se iluminará en amarillo).
4. *(Opcional)* Activa el botón **Remoto (Remote)** en `Input: SMK-37 Pro Midi` y `MIDIIN2 (SMK-37 Pro Midi)` para mapear las 8 perillas/knobs.
5. En tu pista MIDI con sintetizador o plugin VST, asegúrate de que **MIDI From** esté en `All Inputs` y que el botón de **Armar grabación (círculo rojo)** esté activado (o Monitor en `In`).

---

### 2. FL Studio
1. Ve a **Options > Audio Settings**.
2. En **Input / Output**, selecciona `M-VAVE SMK-37 Pro ASIO`.
3. Haz clic en **Show ASIO Panel** si deseas cambiar ajustes adicionales.

### 3. REAPER
1. Ve a **Options > Preferences > Audio > Device**.
2. **Audio system**: Selecciona `ASIO`.
3. **ASIO Driver**: Selecciona `M-VAVE SMK-37 Pro ASIO`.
4. Activa las entradas y salidas (1 a 2).

### 4. Cubase / Studio One
1. Ve a la configuración de dispositivo de audio (**Studio Setup > Audio System**).
2. Selecciona `M-VAVE SMK-37 Pro ASIO` como controlador principal.

---

## 🎛️ Panel de Control

Puedes abrir la interfaz de configuración en cualquier momento sin abrir un DAW ejecutando:
```cmd
SMK37Pro_ControlPanel.exe
```
Permite:
- Visualizar el dispositivo de audio USB detectado en tiempo real.
- Seleccionar el tamaño de búfer ASIO deseado con cálculo instantáneo de latencia en milisegundos.
- Alternar entre el modo **WASAPI Exclusive** (latencia ultra-baja y bypass del mezclador del sistema) y modo **Compartido** (permite reproducir música o YouTube mientras produces).

---

## 🔨 Compilación desde Código Fuente

El driver se compila de forma estática con **LLVM MinGW** o **GCC/MinGW-w64** (64-bit):

```cmd
build_driver.bat
```

Requisitos:
- `clang++` o `g++` (x86_64) en el `PATH` del sistema.
- Cabeceras estándar de Windows SDK (`windows.h`, `audioclient.h`, `avrt.h`, `commctrl.h`).

---

## 🧪 Pruebas Automatizadas de Verificación

La carpeta `tests/` contiene utilidades de prueba para validar la integridad del driver:
- `test_timestamp.cpp`: Verifica la alineación de timestamps nanosegundo a nanosegundo con el reloj QPC del sistema.
- `test_robustness.cpp`: Prueba transiciones de tamaño de búfer en caliente (32 a 2048 samples) en modo exclusivo y compartido.
- `test_long_stream.cpp`: Prueba de resistencia de reproducción continua prolongada (30+ segundos) para verificar estabilidad de callbacks y ausencia de deriva de latencia.
- `test_control_panel_sim.cpp`: Simula la apertura y cierre del panel de control desde el hilo de un DAW.
- `test_midi.py`: Comprueba la recepción directa de notas y perillas MIDI a través del endpoint USB.

---

## 🗑️ Desinstalación

Para desregistrar el driver y eliminar sus claves COM del sistema:
```cmd
uninstall_driver.bat
```

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.
