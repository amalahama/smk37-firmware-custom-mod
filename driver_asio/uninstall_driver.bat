@echo off
setlocal enabledelayedexpansion
title M-VAVE SMK-37 Pro ASIO Driver Uninstaller

openfiles >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Administrator privileges required.
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

set "INSTALL_DIR=%ProgramFiles%\M-VAVE SMK-37 Pro ASIO"
set "TARGET_DLL=!INSTALL_DIR!\SMK37Pro_ASIO.dll"
set "CLSID={7C38B80E-5AED-4B33-A751-6CE34EC4C701}"

if exist "!TARGET_DLL!" (
    regsvr32.exe /u /s "!TARGET_DLL!"
)

reg delete "HKLM\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO" /f >nul 2>&1
reg delete "HKLM\SOFTWARE\WOW6432Node\ASIO\M-VAVE SMK-37 Pro ASIO" /f >nul 2>&1
reg delete "HKCU\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO" /f >nul 2>&1
reg delete "HKCR\CLSID\!CLSID!" /f >nul 2>&1
reg delete "HKCU\Software\Classes\CLSID\!CLSID!" /f >nul 2>&1

if exist "!INSTALL_DIR!" (
    rmdir /s /q "!INSTALL_DIR!" >nul 2>&1
)

echo.
echo [SUCCESS] M-VAVE SMK-37 Pro ASIO Driver completely uninstalled.
echo.
if "%1"=="" pause
