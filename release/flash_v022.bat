@echo off
setlocal
title M-VAVE SMK-37 Pro Firmware Flasher v022

echo =======================================================================
echo          M-VAVE SMK-37 Pro - Custom Firmware Flasher v022
echo       (Woovebox 3.0 BLE-MIDI Stability ^& Low-Latency DAW Fix)
echo =======================================================================
echo.
echo Please ensure:
echo  1. Your M-VAVE SMK-37 Pro keyboard is connected via USB cable.
echo  2. Close any DAW, MIDI monitor, or M-VAVE software before flashing.
echo.
pause

echo.
echo Scanning for SMK-37 Pro MIDI interface...
python smk_ota_win.py scan
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Python is not installed or not in PATH, or device was not found.
    echo Please make sure Python 3.7+ is installed.
    pause
    exit /b 1
)

echo.
echo Starting firmware flashing with SMK-37_Pro_custom_022.fwsc...
echo DO NOT UNPLUG THE USB CABLE DURING FLASHING!
echo.
python smk_ota_win.py flash SMK-37_Pro_custom_022.fwsc

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =======================================================================
    echo [SUCCESS] Firmware v022 flashed successfully!
    echo Your SMK-37 Pro keyboard will now reboot with custom firmware v022.
    echo =======================================================================
) else (
    echo.
    echo =======================================================================
    echo [ERROR] Flashing failed or was interrupted.
    echo Try disconnecting and reconnecting the USB cable and running this again.
    echo =======================================================================
)

echo.
pause
