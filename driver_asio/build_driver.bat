@echo off
setlocal enabledelayedexpansion
title Building M-VAVE SMK-37 Pro ASIO Driver

echo ========================================================
echo   Compiling M-VAVE SMK-37 Pro Dedicated ASIO Driver
echo ========================================================
echo.

if defined CXX if exist "!CXX!" goto found_cxx

where clang++ >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "CXX=clang++"
    goto found_cxx
)

where g++ >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "CXX=g++"
    goto found_cxx
)

if exist "C:\Users\amala\tools\llvm-mingw-20260616-ucrt-x86_64\bin\clang++.exe" (
    set "CXX=C:\Users\amala\tools\llvm-mingw-20260616-ucrt-x86_64\bin\clang++.exe"
    goto found_cxx
)

echo [ERROR] No C++ compiler found (clang++ or g++)!
echo Please ensure MinGW-w64 or Clang is installed and available in PATH.
pause
exit /b 1

:found_cxx
echo [INFO] Using compiler: !CXX!
if not exist "%~dp0bin" mkdir "%~dp0bin"

echo [1/2] Compiling SMK37Pro_ASIO.dll...
"!CXX!" -O2 -s -shared -static -static-libgcc -static-libstdc++ ^
    -Wno-microsoft-exception-spec -I"%~dp0include" ^
    -o "%~dp0bin\SMK37Pro_ASIO.dll" ^
    "%~dp0src\smk37pro_asio.cpp" "%~dp0src\dllmain.cpp" "%~dp0src\smk37pro_asio.def" ^
    -lole32 -luuid -lgdi32 -lavrt -lcomctl32

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Compilation of SMK37Pro_ASIO.dll failed!
    pause
    exit /b !ERRORLEVEL!
)
echo [OK] bin\SMK37Pro_ASIO.dll generated successfully.

echo.
echo [2/2] Compiling SMK37Pro_ControlPanel.exe...
"!CXX!" -O2 -s -mwindows -static -static-libgcc -static-libstdc++ ^
    -I"%~dp0include" ^
    -o "%~dp0bin\SMK37Pro_ControlPanel.exe" ^
    "%~dp0src\control_panel_main.cpp" ^
    -lole32 -luuid

if !ERRORLEVEL! neq 0 (
    echo [ERROR] Compilation of SMK37Pro_ControlPanel.exe failed!
    pause
    exit /b !ERRORLEVEL!
)
echo [OK] bin\SMK37Pro_ControlPanel.exe generated successfully.

set "LOCAL_CACHE=%LOCALAPPDATA%\M-VAVE SMK-37 Pro ASIO"
if not exist "!LOCAL_CACHE!" mkdir "!LOCAL_CACHE!" 2>nul
copy /y "%~dp0bin\SMK37Pro_ASIO.dll" "!LOCAL_CACHE!\SMK37Pro_ASIO.dll" >nul 2>nul
copy /y "%~dp0bin\SMK37Pro_ControlPanel.exe" "!LOCAL_CACHE!\SMK37Pro_ControlPanel.exe" >nul 2>nul
echo [OK] Cached to !LOCAL_CACHE!

echo.
echo ========================================================
echo   BUILD COMPLETE!
echo   Output files located in driver_asio\bin\
echo ========================================================
pause
