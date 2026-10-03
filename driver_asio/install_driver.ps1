#Requires -RunAsAdministrator
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  M-VAVE SMK-37 Pro Dedicated ASIO Driver Installer" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SrcDll = Join-Path $ScriptDir "bin\SMK37Pro_ASIO.dll"
$SrcExe = Join-Path $ScriptDir "bin\SMK37Pro_ControlPanel.exe"

if (-not (Test-Path $SrcDll)) {
    $LocalCache = "$env:LOCALAPPDATA\M-VAVE SMK-37 Pro ASIO"
    if (Test-Path (Join-Path $LocalCache "SMK37Pro_ASIO.dll")) {
        $SrcDll = Join-Path $LocalCache "SMK37Pro_ASIO.dll"
        $SrcExe = Join-Path $LocalCache "SMK37Pro_ControlPanel.exe"
    }
}

if (-not (Test-Path $SrcDll)) {
    Write-Error "Driver binary not found! Please build the driver first or download the release."
    exit 1
}

$InstallDir = "$env:ProgramFiles\M-VAVE SMK-37 Pro ASIO"
Write-Host "Installing to: $InstallDir" -ForegroundColor Yellow
if (-not (Test-Path $InstallDir)) {
    New-Item -Path $InstallDir -ItemType Directory -Force | Out-Null
}

Copy-Item -Path $SrcDll -Destination "$InstallDir\SMK37Pro_ASIO.dll" -Force
if (Test-Path $SrcExe) {
    Copy-Item -Path $SrcExe -Destination "$InstallDir\SMK37Pro_ControlPanel.exe" -Force
}

$TargetDll = "$InstallDir\SMK37Pro_ASIO.dll"
$Clsid = "{7C38B80E-5AED-4B33-A751-6CE34EC4C701}"

Write-Host "Registering COM InprocServer32..." -ForegroundColor Yellow
Start-Process "regsvr32.exe" -ArgumentList "/s `"$TargetDll`"" -Wait

Write-Host "Registering HKLM ASIO driver keys for DAWs (Ableton Live, FL Studio, Cubase, Reaper)..." -ForegroundColor Yellow

# HKLM 64-bit ASIO
$HklmAsio = "HKLM:\SOFTWARE\ASIO\M-VAVE SMK-37 Pro ASIO"
if (-not (Test-Path $HklmAsio)) { New-Item -Path $HklmAsio -Force | Out-Null }
Set-ItemProperty -Path $HklmAsio -Name "CLSID" -Value $Clsid -Type String
Set-ItemProperty -Path $HklmAsio -Name "Description" -Value "M-VAVE SMK-37 Pro ASIO" -Type String

# HKLM WOW6432Node ASIO (for 32-bit hosts)
$WowAsio = "HKLM:\SOFTWARE\WOW6432Node\ASIO\M-VAVE SMK-37 Pro ASIO"
if (-not (Test-Path $WowAsio)) { New-Item -Path $WowAsio -Force | Out-Null }
Set-ItemProperty -Path $WowAsio -Name "CLSID" -Value $Clsid -Type String
Set-ItemProperty -Path $WowAsio -Name "Description" -Value "M-VAVE SMK-37 Pro ASIO" -Type String

# HKCR CLSID
$HkcrClsid = "HKCR:\CLSID\$Clsid"
if (-not (Test-Path $HkcrClsid)) { New-Item -Path $HkcrClsid -Force | Out-Null }
Set-Item -Path $HkcrClsid -Value "M-VAVE SMK-37 Pro ASIO"
$HkcrInproc = "$HkcrClsid\InprocServer32"
if (-not (Test-Path $HkcrInproc)) { New-Item -Path $HkcrInproc -Force | Out-Null }
Set-Item -Path $HkcrInproc -Value $TargetDll
Set-ItemProperty -Path $HkcrInproc -Name "ThreadingModel" -Value "Apartment" -Type String

# HKCU CLSID
$HkcuClsid = "HKCU:\Software\Classes\CLSID\$Clsid"
if (-not (Test-Path $HkcuClsid)) { New-Item -Path $HkcuClsid -Force | Out-Null }
Set-Item -Path $HkcuClsid -Value "M-VAVE SMK-37 Pro ASIO"
$HkcuInproc = "$HkcuClsid\InprocServer32"
if (-not (Test-Path $HkcuInproc)) { New-Item -Path $HkcuInproc -Force | Out-Null }
Set-Item -Path $HkcuInproc -Value $TargetDll
Set-ItemProperty -Path $HkcuInproc -Name "ThreadingModel" -Value "Apartment" -Type String

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  [SUCCESS] Driver installed and registered successfully!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "Ableton Live will now detect 'M-VAVE SMK-37 Pro ASIO' under Audio Preferences."
Write-Host ""
