#!/usr/bin/env bash
#
# Nebula Commander client installer for Linux (systemd).
# Installs the Nebula binary + ncclient, enrolls this machine, and registers the
# ncclient background service so the tunnel comes up at boot.
#
# Usage:
#   sudo ./install-linux.sh --code XXXXXXXX [--server https://mesh.atomcare.io]
#   # or non-interactively via env:
#   sudo NEBULA_COMMANDER_SERVER=https://mesh.atomcare.io NEBULA_COMMANDER_CODE=XXXX ./install-linux.sh
#
set -euo pipefail

REPO="BilalBouk/nebula-commander"
NEBULA_VERSION="v1.10.2"
SERVER="${NEBULA_COMMANDER_SERVER:-https://mesh.atomcare.io}"
CODE="${NEBULA_COMMANDER_CODE:-}"

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
  x86_64|amd64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1;;
esac

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing required tool: $1" >&2; exit 1; }; }
need curl; need tar; need systemctl

echo "==> Installing Nebula ${NEBULA_VERSION} (${ARCH})"
tmp="$(mktemp -d)"
curl -fsSL -o "$tmp/nebula.tar.gz" \
  "https://github.com/slackhq/nebula/releases/download/${NEBULA_VERSION}/nebula-linux-${ARCH}.tar.gz"
tar -C /usr/local/bin -xzf "$tmp/nebula.tar.gz" nebula nebula-cert
chmod +x /usr/local/bin/nebula /usr/local/bin/nebula-cert

echo "==> Installing ncclient (latest release)"
curl -fsSL -o /usr/local/bin/ncclient \
  "https://github.com/${REPO}/releases/latest/download/ncclient-linux-${ARCH}"
chmod +x /usr/local/bin/ncclient
rm -rf "$tmp"

if [ -z "$CODE" ]; then
  cat >&2 <<EOF

Binaries installed. No enrollment code was provided, so enrollment + the service
were skipped. Get a code from the Nebula Commander UI (Nodes -> Enroll), then run:

  sudo ncclient --server ${SERVER} enroll --code XXXXXXXX
  sudo NEBULA_COMMANDER_SERVER=${SERVER} NEBULA_COMMANDER_NEBULA=/usr/local/bin/nebula ncclient install --non-interactive
  sudo systemctl start ncclient
EOF
  exit 0
fi

echo "==> Enrolling this machine"
ncclient --server "$SERVER" enroll --code "$CODE"

echo "==> Installing + starting the ncclient service"
NEBULA_COMMANDER_SERVER="$SERVER" \
NEBULA_COMMANDER_NEBULA="/usr/local/bin/nebula" \
  ncclient install --non-interactive
systemctl start ncclient

echo
echo "Done. The ncclient service is running (systemctl status ncclient)."
echo "Nebula will create the 'atommesh' interface once it connects to the lighthouse."
