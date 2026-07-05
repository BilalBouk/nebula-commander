@echo off
setlocal
REM ============================================================================
REM Nebula Commander client installer for Windows (batch — no PowerShell policy).
REM Downloads + installs the MSI (ncclient + Nebula + wintun + background service),
REM then enrolls this machine so the service brings the tunnel up at boot.
REM
REM Usage (double-click, or from a command prompt):
REM   install-windows.cmd <ENROLLMENT_CODE> [SERVER_URL]
REM   install-windows.cmd ZRXDFVWMVHTZ34C8
REM   install-windows.cmd ZRXDFVWMVHTZ34C8 https://mesh.atomcare.io
REM ============================================================================

set "REPO=BilalBouk/nebula-commander"
set "MSIURL=https://github.com/%REPO%/releases/latest/download/NebulaCommander-windows-amd64.msi"

set "CODE=%~1"
set "SERVER=%~2"
if "%SERVER%"=="" set "SERVER=https://mesh.atomcare.io"

if "%CODE%"=="" (
  echo.
  echo   Usage: install-windows.cmd ^<ENROLLMENT_CODE^> [SERVER_URL]
  echo   Example: install-windows.cmd ZRXDFVWMVHTZ34C8
  echo.
  echo   Get an enrollment code from the Nebula Commander UI: Nodes -^> Enroll
  echo.
  pause
  exit /b 1
)

REM --- Require administrator; self-elevate if not (uses powershell -Command, which
REM     is NOT affected by the .ps1 script execution policy). ---
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting administrator privileges...
  powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%CODE% %SERVER%' -Verb RunAs"
  exit /b
)

set "MSI=%TEMP%\NebulaCommander-windows-amd64.msi"
set "NCCLIENT=%ProgramFiles%\Nebula Commander\ncclient.exe"
if not exist "%NCCLIENT%" set "NCCLIENT=%ProgramW6432%\Nebula Commander\ncclient.exe"

echo ==^> Downloading MSI from the latest release...
where curl >nul 2>&1
if "%errorlevel%"=="0" (
  curl -L -f -o "%MSI%" "%MSIURL%"
) else (
  powershell -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%MSIURL%' -OutFile '%MSI%'"
)
if not exist "%MSI%" (
  echo Download failed. Check your internet connection and try again.
  pause
  exit /b 1
)

echo ==^> Installing MSI (silent)...
msiexec /i "%MSI%" /qn /norestart
set "MSIRC=%errorlevel%"
if not "%MSIRC%"=="0" if not "%MSIRC%"=="3010" (
  echo MSI install failed with exit code %MSIRC%.
  pause
  exit /b 1
)

if not exist "%NCCLIENT%" (
  echo ncclient.exe not found at "%NCCLIENT%" after install.
  pause
  exit /b 1
)

echo ==^> Enrolling this machine (machine scope)...
"%NCCLIENT%" --server %SERVER% enroll --machine --code %CODE%
if not "%errorlevel%"=="0" (
  echo Enrollment failed. The code may be expired — generate a new one in the UI.
  pause
  exit /b 1
)

echo ==^> Restarting the ncclient service...
net stop ncclient >nul 2>&1
net start ncclient >nul 2>&1

echo.
echo Done. Nebula will create the 'atommesh' adapter once it connects to the lighthouse.
echo   Service state:
sc query ncclient | findstr /i "STATE"
echo   Adapter:  ipconfig ^| findstr atommesh
echo.
pause
exit /b 0
