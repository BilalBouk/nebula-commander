# Client install scripts

One script per platform. Each downloads the matching client from the latest
[GitHub release](https://github.com/BilalBouk/nebula-commander/releases/latest),
installs Nebula, enrolls the machine, and sets it up to run as a background
service/daemon at boot. Get a one-time **enrollment code** from the Commander UI
(Nodes → Enroll) first; each machine needs its own code.

The default server is `https://mesh.atomcare.io`; override with `--server`.

## Linux (systemd)

```bash
curl -fsSLO https://raw.githubusercontent.com/BilalBouk/nebula-commander/security-hardening/install/install-linux.sh
sudo bash install-linux.sh --code XXXXXXXX
```

## macOS (launchd)

```bash
curl -fsSLO https://raw.githubusercontent.com/BilalBouk/nebula-commander/security-hardening/install/install-macos.sh
sudo bash install-macos.sh --code XXXXXXXX
```

The binaries are unsigned; the script clears the Gatekeeper quarantine flag so
they run.

## Windows (MSI + service)

Download [install-windows.cmd](https://raw.githubusercontent.com/BilalBouk/nebula-commander/security-hardening/install/install-windows.cmd),
then double-click it (or run from a command prompt) with your enrollment code:

```
install-windows.cmd XXXXXXXX
```

The script self-elevates (UAC prompt), downloads and installs the MSI (ncclient +
Nebula + wintun.dll + the `ncclient` Windows service), and enrolls in machine
scope so the service runs with no user logged in. A batch file is used instead of
PowerShell so it runs regardless of the PowerShell script execution policy, which
blocks `.ps1` files by default on most machines.

> A PowerShell version (`install-windows.ps1`) is also provided for anyone who
> prefers it, but it requires an execution-policy bypass on locked-down machines.

---

Once connected, Nebula creates the **`atommesh`** interface. Verify:
- Linux/macOS: `ip addr show atommesh` / `ifconfig atommesh`
- Windows: `Get-NetAdapter atommesh`
