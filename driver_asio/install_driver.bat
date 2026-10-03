@echo off
setlocal enabledelayedexpansion
title M-VAVE SMK-37 Pro ASIO Driver Installer

echo ========================================================
echo   M-VAVE SMK-37 Pro Dedicated ASIO Driver Installer
echo ========================================================
echo.

:: 1. Identify Source Files
set "LOCAL_CACHE=%LOCALAPPDATA%\M-VAVE SMK-37 Pro ASIO"
if "%LOCAL_CACHE%"=="" set "LOCAL_CACHE=%USERPROFILE%\AppData\Local\M-VAVE SMK-37 Pro ASIO"
if not exist "!LOCAL_CACHE!" mkdir "!LOCAL_CACHE!" 2>nul

set "SRC_DIR=%~dp0"
set "SRC_DLL=%SRC_DIR%bin\SMK37Pro_ASIO.dll"
set "SRC_EXE=%SRC_DIR%bin\SMK37Pro_ControlPanel.exe"

:: If accessible (unelevated with drive O: mapped), update local cache immediately
if exist "!SRC_DLL!" (
    copy /y "!SRC_DLL!" "!LOCAL_CACHE!\SMK37Pro_ASIO.dll" >nul 2>nul
    if exist "!SRC_EXE!" copy /y "!SRC_EXE!" "!LOCAL_CACHE!\SMK37Pro_ControlPanel.exe" >nul 2>nul
)

:: If SRC_DLL is not directly accessible (e.g. elevated session without drive O:), load from local cache
if not exist "!SRC_DLL!" (
    if exist "!LOCAL_CACHE!\SMK37Pro_ASIO.dll" (
        set "SRC_DLL=!LOCAL_CACHE!\SMK37Pro_ASIO.dll"
        set "SRC_EXE=!LOCAL_CACHE!\SMK37Pro_ControlPanel.exe"
    )
)

:: 2. Check for Administrator Privileges
openfiles >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Administrator privileges required for HKLM ASIO registration.
    echo [INFO] Requesting elevation via UAC...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/k \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

if not exist "!SRC_DLL!" (
    echo [ERROR] Driver binary not found: "!SRC_DLL!"
    echo Please compile the driver first using build_driver.bat
    pause
    exit /b 1
)

:: 3. Target Installation Directory in C:\Program Files\
set "INSTALL_DIR=%ProgramFiles%\M-VAVE SMK-37 Pro ASIO"
echo Installing from: "!SRC_DLL!"
echo Installing to  : "!INSTALL_DIR!"...
if not exist "!INSTALL_DIR!" mkdir "!INSTALL_DIR!"

copy /y "!SRC_DLL!" "!INSTALL_DIR!\SMK37Pro_ASIO.dll"
if exist "!SRC_EXE!" copy /y "!SRC_EXE!" "!INSTALL_DIR!\SMK37Pro_ControlPanel.exe"

set "TARGET_DLL=!INSTALL_DIR!\SMK37Pro_ASIO.dll"
if not exist "!TARGET_DLL!" (
    echo [ERROR] Failed to copy driver to "!INSTALL_DIR!"!
    pause
    exit /b 1
)

:: 4. Register COM in-process server with regsvr32
echo Registering COM InprocServer32...
regsvr32.exe /s "!TARGET_DLL!"

:: 5. Write mandatory Steinberg ASIO keys in HKLM (for 64-bit Ableton Live, FL Studio, Reaper, Cubase)
echo Registering HKLM ASIO driver entries...
set "CLSID={7C38B80E-5AED-4B33-A751-6CE34EC4C701}"

reg add "HKLM\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO" /v CLSID /t REG_SZ /d "!CLSID!" /f >nul
reg add "HKLM\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO" /v Description /t REG_SZ /d "M-VAVE SMK-37 Pro ASIO" /f >nul

reg add "HKLM\SOFTWARE\WOW6432Node\ASIO\M-VAVE SMK-37 Pro ASIO" /v CLSID /t REG_SZ /d "!CLSID!" /f >nul
reg add "HKLM\SOFTWARE\WOW6432Node\ASIO\M-VAVE SMK-37 Pro ASIO" /v Description /t REG_SZ /d "M-VAVE SMK-37 Pro ASIO" /f >nul

reg add "HKCR\CLSID\!CLSID!" /ve /t REG_SZ /d "M-VAVE SMK-37 Pro ASIO" /f >nul
reg add "HKCR\CLSID\!CLSID!\InprocServer32" /ve /t REG_SZ /d "!TARGET_DLL!" /f >nul
reg add "HKCR\CLSID\!CLSID!\InprocServer32" /v ThreadingModel /t REG_SZ /d "Apartment" /f >nul

reg add "HKCU\Software\Classes\CLSID\!CLSID!" /ve /t REG_SZ /d "M-VAVE SMK-37 Pro ASIO" /f >nul
reg add "HKCU\Software\Classes\CLSID\!CLSID!\InprocServer32" /ve /t REG_SZ /d "!TARGET_DLL!" /f >nul
reg add "HKCU\Software\Classes\CLSID\!CLSID!\InprocServer32" /v ThreadingModel /t REG_SZ /d "Apartment" /f >nul

echo.
echo ========================================================
echo   [SUCCESS] M-VAVE SMK-37 Pro ASIO Driver INSTALLED!
echo ========================================================
echo.
echo Binary Location : !TARGET_DLL!
echo Registry Entry  : HKLM\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO
echo Threading Model : Apartment (Steinberg ASIO compliant)
echo Supported DAWs  : Ableton Live (64-bit), FL Studio, Reaper, Cubase, etc.
echo.
echo Setup Instructions for Ableton Live:
echo 1. Connect your M-VAVE SMK-37 Pro via USB.
echo 2. Open Ableton Live.
echo 3. Open Options -^> Preferences -^> Audio.
echo 4. Set Driver Type: "ASIO".
echo 5. Set Audio Device: "M-VAVE SMK-37 Pro ASIO".
echo 6. Click "Hardware Setup" to open the Control Panel and configure buffer size.
echo.
pause
