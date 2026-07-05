# Nebula Commander Windows Tray App

System-tray application for Windows: enroll with a one-time code, poll for config/certs, optionally run Nebula, and toggle auto-start at login.

## Do I need a system service or network adapter?

- **Prefer the MSI service for unattended machines.** The MSI installer (see [installer/windows](../../installer/windows/README.md)) registers the **ncclient Windows service** (WinSW, LocalSystem, auto-start): it runs with no one logged in, needs no per-user elevation, and stores token/config machine-wide under `%ProgramData%\nebula-commander`. The tray app remains for interactive use; **do not run both at once** (both would manage Nebula). **Start at login** in the tray only adds a Registry `HKCU\...\Run` entry for the signed-in user.

- **Nebula’s virtual network adapter.** When you use **Start polling** and Nebula is running, the Nebula binary creates a virtual network interface (Nebula on Windows uses [Wintun](https://www.wintun.net/)). No separate driver install is required for typical use: the official Nebula Windows release works out of the box. The first time Nebula creates the interface, Windows may show a one-time prompt to trust the driver. If you see errors like "create wintun interface failed", try running the tray (or `nebula.exe`) once as Administrator, or see [Nebula’s Windows documentation](https://github.com/slackhq/nebula#windows) and [Wintun](https://www.wintun.net/) for troubleshooting.

## Run from source

From the **nebula-commander** repo root (parent of `client/`):

```bash
pip install -r client/windows/requirements.txt
# Also need ncclient (requests); from repo root:
pip install -e client/
python -m client.windows.tray
```

Or with `pythonw` to avoid a console window:

```bash
pythonw -m client.windows.tray
```

## Settings

- Stored in `%APPDATA%\nebula-commander\settings.json` (server URL, output dir, poll interval, optional Nebula path).
- Token is shared with ncclient: `~/.config/nebula-commander/token` (or same dir as settings on Windows).

## Bundled Nebula

When built with PyInstaller (see below), the installer can bundle the official Nebula Windows binary. The Settings dialog defaults the "Nebula path" to the bundled `nebula.exe` when present; you can override with a custom path or leave empty to use `nebula` from PATH.

## Auto-start at login

Use the tray menu **Start at login** (checkable). When enabled, the app is registered in the Windows Registry (`HKCU\...\Run`) so it starts when you log in. When running from the built `.exe`, the executable path is registered; when running from source, a small launcher script in `%APPDATA%\nebula-commander\` is registered.

## Build (PyInstaller)

From **nebula-commander** repo root:

1. Download Nebula Windows binary (see `build.py`).
2. Run the build script to produce `ncclient-tray.exe` and optionally bundle `nebula.exe`:

```bash
cd client/windows
pip install -r requirements.txt pyinstaller
python build.py
```

Output is in `client/windows/dist/` (or as configured in the spec). See `build.py` and `ncclient-tray.spec` for details.
