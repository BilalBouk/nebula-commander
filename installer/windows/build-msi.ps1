# Build Nebula Commander MSI. Run from installer/windows/.
# Requires: WiX 5, and redist/ncclient.exe + redist/ncclient-tray.exe +
#           redist/nebula.exe (official Nebula release) +
#           redist/ncclient-service.exe (WinSW, renamed)
# Usage: .\build-msi.ps1 [-Version "0.1.12"]

param(
    [string]$Version = "0.0.0"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$redist = Join-Path $ScriptDir "redist"
foreach ($exe in @("ncclient.exe", "ncclient-tray.exe", "nebula.exe", "ncclient-service.exe", "wintun.dll")) {
    $path = Join-Path $redist $exe
    if (-not (Test-Path $path)) {
        Write-Error "Missing $path - redist/ needs ncclient.exe, ncclient-tray.exe, nebula.exe, ncclient-service.exe (WinSW) and wintun.dll (from the official Nebula zip: dist\windows\wintun\bin\amd64\wintun.dll)"
    }
}

$out = "NebulaCommander-windows-amd64.msi"
& wix build Product.wxs -ext WixToolset.Util.wixext -o $out -d "Version=$Version" -arch x64
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Built $out"
