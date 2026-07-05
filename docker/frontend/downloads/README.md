# Client binaries served from the UI

Files placed in this directory are copied into the frontend image at build time
to `/usr/share/nginx/html/downloads/` and served by nginx at `/downloads/<file>`.
The **Download Client** page in the UI ([ClientDownload.tsx](../../../frontend/src/pages/ClientDownload.tsx))
links to these exact filenames.

The binaries are large and are **git-ignored** (see `.gitignore` here) — they are
not committed. Stage them locally before building the image.

## Expected filenames

| File | Platform |
|------|----------|
| `ncclient-linux-amd64` | Linux x86_64 |
| `ncclient-linux-arm64` | Linux ARM64 |
| `ncclient-macos-amd64` | macOS Intel |
| `ncclient-macos-arm64` | macOS Apple Silicon |
| `ncclient-windows-amd64.exe` | Windows CLI |
| `ncclient-tray-windows-amd64.exe` | Windows tray app |
| `NebulaCommander-windows-amd64.msi` | Windows MSI installer (service) |

## How to populate

Two ways:

1. **Stage local binaries (self-contained, offline).** Copy the files built by
   the `Build ncclient Binaries` workflow (or downloaded from a release) into
   this folder, then build normally:
   ```bash
   docker compose -f docker/docker-compose.yml build frontend
   ```
   Any file present here wins; the image needs no internet access.

2. **Fetch from a GitHub release at build time.** Leave this folder empty and
   build with `DOWNLOAD_BINARIES=1`; the Dockerfile downloads the matching
   assets from the `GITHUB_REPO` release for `VERSION`:
   ```bash
   docker build -f docker/frontend/Dockerfile \
     --build-arg DOWNLOAD_BINARIES=1 \
     --build-arg VERSION=0.3.0 \
     --build-arg GITHUB_REPO=BilalBouk/nebula-commander \
     -t nebula-commander-frontend ..
   ```
   This requires a published release with those assets.
