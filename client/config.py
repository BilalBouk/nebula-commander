"""
Shared config and paths for ncclient (tray, CLI).
Settings are stored in settings.json. Config dir is standalone (no token path).

Two scopes:
- user scope (default): per-user dirs (%APPDATA% / ~/.config) — tray and interactive CLI.
- machine scope: ProgramData (Windows) or /etc (POSIX) — used when ncclient runs as a
  background service, so enrollment done by an admin and the service account (LocalSystem,
  root) see the same token/settings. Enabled with NEBULA_COMMANDER_MACHINE_SCOPE=1 or the
  --machine flag; auto-detected when running under the Windows LocalSystem profile.
"""
import json
import os
import subprocess
import sys

__all__ = [
    "config_dir",
    "machine_scope",
    "machine_config_dir",
    "settings_path",
    "load_settings",
    "save_settings",
]

_machine_dir_secured = False


def machine_scope() -> bool:
    """True when token/settings should live in machine-wide locations."""
    v = os.environ.get("NEBULA_COMMANDER_MACHINE_SCOPE", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    if sys.platform == "win32":
        # A service running as LocalSystem resolves ~ to the systemprofile dir.
        return "systemprofile" in os.path.expanduser("~").lower()
    return False


def machine_config_dir() -> str:
    """Machine-wide base directory (no ACL setup; see config_dir)."""
    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
        return os.path.join(program_data, "nebula-commander")
    return "/etc/nebula-commander"


def _secure_machine_dir(path: str) -> None:
    """Restrict the machine dir to SYSTEM/Administrators (it holds the device token
    and Nebula private keys). Windows: break inheritance so BUILTIN\\Users lose the
    default ProgramData read access. POSIX: 0700."""
    global _machine_dir_secured
    if _machine_dir_secured:
        return
    _machine_dir_secured = True
    if sys.platform == "win32":
        try:
            # SIDs, not names, so this works on non-English Windows:
            # S-1-5-18 = SYSTEM, S-1-5-32-544 = Administrators.
            subprocess.run(
                [
                    "icacls", path,
                    "/inheritance:r",
                    "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F",
                ],
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    else:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def config_dir() -> str:
    """Base directory for settings and other config (e.g. nebula downloads)."""
    if machine_scope():
        path = machine_config_dir()
        os.makedirs(path, exist_ok=True)
        _secure_machine_dir(path)
        return path
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(appdata, "nebula-commander")
    return os.path.join(os.path.expanduser("~"), ".config", "nebula-commander")


def settings_path() -> str:
    """Path to settings.json (server, output_dir, interval, nebula_path)."""
    return os.path.join(config_dir(), "settings.json")


def load_settings() -> dict:
    """Load settings from disk. Returns dict with server, output_dir, interval, nebula_path (or empty)."""
    path = settings_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    """Write settings to disk."""
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
