# Update driver files and registration
$ErrorActionPreference = "Stop"

$Clsid = "{7C38B80E-5AED-4B33-A751-6CE34EC4C701}"
$SrcDir = "O:\PROGRAMACION\GEMINI ANTIGRAVITY\smk37mod\driver_asio"
$SrcDll = "$SrcDir\bin\SMK37Pro_ASIO.dll"
$SrcExe = "$SrcDir\bin\SMK37Pro_ControlPanel.exe"
$InstallDir = "$env:ProgramFiles\M-VAVE SMK-37 Pro ASIO"

Write-Host "1. Testing local compiled DLL with COM..." -ForegroundColor Cyan
$hkcuInproc = "HKCU:\Software\Classes\CLSID\$Clsid\InprocServer32"
if (-not (Test-Path $hkcuInproc)) {
    New-Item -Path $hkcuInproc -Force | Out-Null
}
Set-Item -Path $hkcuInproc -Value $SrcDll
Set-ItemProperty -Path $hkcuInproc -Name "ThreadingModel" -Value "Apartment"
Write-Host "   HKCU InprocServer32 set to $SrcDll"

# Run test_asio.exe to verify COM CoCreateInstance with CLSID
Write-Host "2. Running test_asio.exe..." -ForegroundColor Cyan
& "$SrcDir\test_asio.exe"

# Now copy to Program Files and update HKLM via elevated process
Write-Host "3. Updating C:\Program Files and HKLM via elevated script..." -ForegroundColor Cyan
$elevateScript = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$InstallDir = '$InstallDir'
if (-not (Test-Path `$InstallDir)) { New-Item -Path `$InstallDir -ItemType Directory -Force }
Copy-Item -Path '$SrcDll' -Destination "`$InstallDir\SMK37Pro_ASIO.dll" -Force
Copy-Item -Path '$SrcExe' -Destination "`$InstallDir\SMK37Pro_ControlPanel.exe" -Force
Start-Process "regsvr32.exe" -ArgumentList "/s `"`$InstallDir\SMK37Pro_ASIO.dll`"" -Wait
"@

$tempScript = "$env:TEMP\update_smk37_driver.ps1"
Set-Content -Path $tempScript -Value $elevateScript
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tempScript`"" -Verb RunAs -Wait

# Verify if Program Files file was updated
$progDll = "$InstallDir\SMK37Pro_ASIO.dll"
if (Test-Path $progDll) {
    $info = Get-Item $progDll
    Write-Host "Program Files DLL LastWriteTime: $($info.LastWriteTime)" -ForegroundColor Green
}
