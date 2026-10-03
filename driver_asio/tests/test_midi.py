import ctypes
from ctypes import wintypes
import time
import sys

# WinMM definitions
CALLBACK_FUNCTION = 0x00030000
MIM_DATA = 0x3C3
MIM_MOREDATA = 0x3CC

class MIDIINCAPSA(ctypes.Structure):
    _fields_ = [
        ('wMid', wintypes.WORD),
        ('wPid', wintypes.WORD),
        ('vDriverVersion', wintypes.UINT),
        ('szPname', ctypes.c_char * 32),
        ('dwSupport', wintypes.DWORD)
    ]

winmm = ctypes.windll.winmm

def midi_callback(hMidiIn, wMsg, dwInstance, dwParam1, dwParam2):
    if wMsg == MIM_DATA or wMsg == MIM_MOREDATA:
        status = dwParam1 & 0xFF
        data1 = (dwParam1 >> 8) & 0xFF
        data2 = (dwParam1 >> 16) & 0xFF
        msg_type = status & 0xF0
        channel = (status & 0x0F) + 1
        
        # Filter out active sensing (0xFE) and clock (0xF8)
        if status in (0xFE, 0xF8):
            return
            
        if msg_type == 0x90:
            if data2 > 0:
                print(f"[MIDI IN] NOTE ON  - Canal: {channel}, Nota: {data1}, Velocidad: {data2}")
            else:
                print(f"[MIDI IN] NOTE OFF - Canal: {channel}, Nota: {data1}, Velocidad: 0")
        elif msg_type == 0x80:
            print(f"[MIDI IN] NOTE OFF - Canal: {channel}, Nota: {data1}, Velocidad: {data2}")
        elif msg_type == 0xB0:
            print(f"[MIDI IN] CC       - Canal: {channel}, CC#: {data1}, Valor: {data2}")
        elif msg_type == 0xE0:
            pitch = (data2 << 7) | data1
            print(f"[MIDI IN] PITCH    - Canal: {channel}, Valor: {pitch}")
        else:
            print(f"[MIDI IN] RAW: {hex(status)} {hex(data1)} {hex(data2)}")
        sys.stdout.flush()

MIDIINPROC = ctypes.WINFUNCTYPE(None, wintypes.HMETAFILE, wintypes.UINT, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD)
callback_func = MIDIINPROC(midi_callback)

num_devs = winmm.midiInGetNumDevs()
target_dev = -1
for i in range(num_devs):
    caps = MIDIINCAPSA()
    winmm.midiInGetDevCapsA(i, ctypes.byref(caps), ctypes.sizeof(caps))
    name = caps.szPname.decode('latin1', 'ignore')
    if "SMK-37 Pro Midi" in name and "Port" not in name and "MIDIIN" not in name:
        target_dev = i
        print(f"Encontrado dispositivo: ID {i} -> {name}")
        break

if target_dev == -1 and num_devs > 0:
    target_dev = 0

if target_dev == -1:
    print("No se encontraron dispositivos MIDI.")
    sys.exit(1)

hMidi = wintypes.HANDLE()
res = winmm.midiInOpen(ctypes.byref(hMidi), target_dev, callback_func, 0, CALLBACK_FUNCTION)
if res != 0:
    print(f"Error abriendo puerto MIDI: {res} (puede que Ableton lo tenga abierto en exclusiva si tiene control surfaces asignadas)")
    sys.exit(1)

winmm.midiInStart(hMidi)
print("Escuchando mensajes MIDI durante 10 segundos... Toca teclas o gira perillas en el teclado...")
sys.stdout.flush()

t_end = time.time() + 10
while time.time() < t_end:
    time.sleep(0.1)

winmm.midiInStop(hMidi)
winmm.midiInClose(hMidi)
print("Fin de la prueba.")
