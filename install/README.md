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

From an **elevated** PowerShell (Run as administrator):

```powershell
irm https://raw.githubusercontent.com/BilalBouk/nebula-commander/security-hardening/install/install-windows.ps1 -OutFile install-windows.ps1
.\install-windows.ps1 -Code XXXXXXXX
```

Installs the MSI (ncclient + Nebula + wintun.dll + the `ncclient` Windows
service) and enrolls in machine scope so the service runs with no user logged in.

---

Once connected, Nebula creates the **`atommesh`** interface. Verify:
- Linux/macOS: `ip addr show atommesh` / `ifconfig atommesh`
- Windows: `Get-NetAdapter atommesh`
