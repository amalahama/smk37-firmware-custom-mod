$destDir = "C:\Users\amala\AppData\Local\M-VAVE SMK-37 Pro ASIO"
if (-not (Test-Path $destDir)) {
    New-Item -Path $destDir -ItemType Directory -Force | Out-Null
}
Copy-Item -Path "bin\SMK37Pro_ASIO.dll" -Destination "$destDir\SMK37Pro_ASIO.dll" -Force
Copy-Item -Path "bin\SMK37Pro_ControlPanel.exe" -Destination "$destDir\SMK37Pro_ControlPanel.exe" -Force
Get-Item "$destDir\SMK37Pro_ASIO.dll" | Select-Object FullName, LastWriteTime, Length
