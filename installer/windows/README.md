# Nebula Commander Windows MSI Installer

WiX 5 installer that installs **ncclient** (CLI), **ncclient-tray** (system tray), **nebula.exe**
(official Nebula binary) and the **ncclient Windows service** (WinSW) to
`%ProgramFiles%\Nebula Commander\`, with optional PATH and Start Menu shortcuts.

## What gets installed

- `ncclient.exe`, `ncclient-tray.exe`, `nebula.exe`
- `ncclient-service.exe` (WinSW) + `ncclient-service.xml` — registered as Windows service
  **ncclient** ("Nebula Commander Client"), LocalSystem, auto-start, restart-on-failure.
- The service runs `ncclient run` with machine scope: token/settings/config live under
  `%ProgramData%\nebula-commander\` (ACL'd to SYSTEM/Administrators), so it works with no
  user logged in. Service logs: `%ProgramData%\nebula-commander\logs\`.

## Post-install: enroll the machine

The service starts at install time and **waits for enrollment** (it does not fail).
From an elevated prompt:

```powershell
& "C:\Program Files\Nebula Commander\ncclient.exe" enroll --machine --server https://your-commander.example.com --code XXXXXXXX
```

The running service picks up the token within seconds and brings the tunnel up.
No re-login, no scheduled tasks, survives reboots.

> Don't run the tray app and the service at the same time — both would try to run Nebula.
> On service-managed machines the tray is optional/legacy.

## Prerequisites (local build)

- [.NET SDK](https://dotnet.microsoft.com/download) (required for the WiX dotnet tool)
- [WiX Toolset 5](https://wixtoolset.org/docs/intro/) (e.g. `dotnet tool install --global wix --version 5.0.2` or install from [releases](https://github.com/wixtoolset/wix/releases))
- Four executables in `redist/`:
  - `redist/ncclient.exe` (from `client/binaries/dist/` after PyInstaller build)
  - `redist/ncclient-tray.exe` (from `client/windows/dist/` after tray build)
  - `redist/nebula.exe` (from the official [Nebula release](https://github.com/slackhq/nebula/releases) `nebula-windows-amd64.zip` — verify the SHA256 against the release `SHASUM256.txt`)
  - `redist/ncclient-service.exe` ([WinSW](https://github.com/winsw/winsw/releases) `WinSW-x64.exe`, renamed)

## Building locally

1. Place the four exes in `installer/windows/redist/` (see above).
2. If you installed WiX 5 via `dotnet tool install -g wix --version 5.0.2`, add the Util extension once (use version 5.0.0 so it matches WiX 5; the default pulls 7.x which is incompatible):
   ```powershell
   wix extension add -g WixToolset.Util.wixext/5.0.0
   ```
3. From `installer/windows/` run:

   ```powershell
   wix build Product.wxs -ext WixToolset.Util.wixext -o NebulaCommander-windows-amd64.msi -d Version=0.1.12 -arch x64
   ```

   Replace `0.1.12` with the version you are building (e.g. from tag `v0.1.12`).

Output: `NebulaCommander-windows-amd64.msi`.

## Other installer behavior

- **Optional feature**: "Add install directory to PATH" so `ncclient` works from any command prompt.
- **Start Menu** shortcuts: "Nebula Commander (CLI)" and "Nebula Commander Tray".
- **Add or Remove Programs**: full uninstall (service is stopped and removed), including PATH
  removal if that feature was installed. Machine data under `%ProgramData%\nebula-commander\`
  (device token, certs, config) is intentionally left behind so an upgrade/reinstall keeps
  the enrollment; delete it manually to fully de-provision a machine.

## CI

The GitHub Actions workflow builds the MSI after building the Windows ncclient and tray exes
(downloading pinned, checksum-verified `nebula.exe` and WinSW), then uploads
`NebulaCommander-windows-amd64.msi` to the release. See `.github/workflows/build-ncclient-binaries.yml`.
