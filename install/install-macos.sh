#!/usr/bin/env bash
#
# Nebula Commander client installer for macOS (launchd).
# Installs the Nebula binary + ncclient, clears the Gatekeeper quarantine (the
# binaries are unsigned), enrolls this machine, and installs a LaunchDaemon so the
# tunnel comes up at boot.
#
# Usage:
#   sudo ./install-macos.sh --code XXXXXXXX [--server https://mesh.atomcare.io]
#
set -euo pipefail

REPO="BilalBouk/nebula-commander"
NEBULA_VERSION="v1.10.2"
SERVER="${NEBULA_COMMANDER_SERVER:-https://mesh.atomcare.io}"
CODE="${NEBULA_COMMANDER_CODE:-}"
PLIST="/Library/LaunchDaemons/io.atomcare.ncclient.plist"

while [ $# -gt 0 ]; do
  case "$1" in
    --code) CODE="$2"; shift 2;;
    --server) SERVER="$2"; shift 2;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

if [ "$(id -u)" != "0" ]; then
  echo "This installer must run as root. Re-run with: sudo $0 ..." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64) ARCH=amd64;;
  arm64) ARCH=arm64;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1;;
esac

echo "==> Installing Nebula ${NEBULA_VERSION}"
tmp="$(mktemp -d)"
# The darwin release is a universal zip (nebula + nebula-cert for both arches).
curl -fsSL -o "$tmp/nebula.zip" \
  "https://github.com/slackhq/nebula/releases/download/${NEBULA_VERSION}/nebula-darwin.zip"
unzip -o -q "$tmp/nebula.zip" -d "$tmp"
install -m755 "$tmp/nebula" /usr/local/bin/nebula
install -m755 "$tmp/nebula-cert" /usr/local/bin/nebula-cert

echo "==> Installing ncclient (latest release, ${ARCH})"
curl -fsSL -o /usr/local/bin/ncclient \
  "https://github.com/${REPO}/releases/latest/download/ncclient-macos-${ARCH}"
chmod +x /usr/local/bin/ncclient

# Unsigned binaries: clear the quarantine flag so macOS will run them.
xattr -d com.apple.quarantine /usr/local/bin/nebula 2>/dev/null || true
xattr -d com.apple.quarantine /usr/local/bin/nebula-cert 2>/dev/null || true
xattr -d com.apple.quarantine /usr/local/bin/ncclient 2>/dev/null || true
rm -rf "$tmp"

if [ -z "$CODE" ]; then
  cat >&2 <<EOF

Binaries installed. No enrollment code was provided, so enrollment + the
LaunchDaemon were skipped. Get a code from the UI (Nodes -> Enroll), then run:

  sudo ncclient --server ${SERVER} enroll --code XXXXXXXX
  sudo $0 --code XXXXXXXX --server ${SERVER}
EOF
  exit 0
fi

echo "==> Enrolling this machine"
ncclient --server "$SERVER" enroll --code "$CODE"

echo "==> Installing LaunchDaemon"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>io.atomcare.ncclient</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/ncclient</string>
    <string>run</string>
    <string>--nebula</string>
    <string>/usr/local/bin/nebula</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>NEBULA_COMMANDER_SERVER</key><string>${SERVER}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/var/log/ncclient.log</string>
  <key>StandardErrorPath</key><string>/var/log/ncclient.err</string>
</dict></plist>
EOF
chmod 644 "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo
echo "Done. LaunchDaemon loaded (logs: /var/log/ncclient.log)."
echo "Nebula will create the 'atommesh' interface once it connects to the lighthouse."
