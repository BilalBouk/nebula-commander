<#
.SYNOPSIS
  Nebula Commander client installer for Windows.
  Downloads and installs the MSI (ncclient + Nebula + wintun + background service),
  then enrolls this machine so the service brings the tunnel up at boot.

.DESCRIPTION
  Must be run from an elevated PowerShell (Run as administrator).

.EXAMPLE
  .\install-windows.ps1 -Code XXXXXXXX
  .\install-windows.ps1 -Code XXXXXXXX -Server https://mesh.atomcare.io
#>
param(
  [Parameter(Mandatory = $true)] [string]$Code,
  [string]$Server = "https://mesh.atomcare.io"
)

$ErrorActionPreference = "Stop"
$Repo = "BilalBouk/nebula-commander"
$MsiUrl = "https://github.com/$Repo/releases/latest/download/NebulaCommander-windows-amd64.msi"
$Ncclient = "C:\Program Files\Nebula Commander\ncclient.exe"

# Require elevation (the service install + machine-scope enroll need admin).
$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
  Write-Error "Run this from an elevated PowerShell (right-click -> Run as administrator)."
  exit 1
}

$msi = Join-Path $env:TEMP "NebulaCommander-windows-amd64.msi"
Write-Host "==> Downloading MSI from latest release"
Invoke-WebRequest -Uri $MsiUrl -OutFile $msi

Write-Host "==> Installing MSI (silent)"
$p = Start-Process msiexec.exe -ArgumentList "/i", "`"$msi`"", "/qn", "/norestart" -Wait -PassThru
if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) {
  Write-Error "MSI install failed with exit code $($p.ExitCode)"
  exit 1
}

if (-not (Test-Path $Ncclient)) {
  Write-Error "ncclient.exe not found at $Ncclient after install."
  exit 1
}

Write-Host "==> Enrolling this machine (machine scope)"
# --server is a global flag and must precede the 'enroll' subcommand.
& $Ncclient --server $Server enroll --machine --code $Code
if ($LASTEXITCODE -ne 0) { Write-Error "Enrollment failed."; exit 1 }

Write-Host "==> Starting the ncclient service"
# The MSI registers + starts the service; restart so it picks up the fresh enrollment.
Restart-Service ncclient -ErrorAction SilentlyContinue
Start-Service ncclient -ErrorAction SilentlyContinue

Start-Sleep -Seconds 8
Write-Host ""
Get-Service ncclient | Format-Table -AutoSize
Write-Host "Done. Nebula will create the 'atommesh' adapter once it connects to the lighthouse."
Write-Host "Check with: Get-NetAdapter atommesh"
