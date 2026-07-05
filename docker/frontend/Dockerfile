# Nebula Commander Frontend
# Node builder stage + nginx image

# Stage 1: Build React app
FROM node:20-alpine AS builder
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps || npm install --legacy-peer-deps

COPY frontend/ .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

RUN apk add --no-cache curl

# Accept version as build arg (e.g. 0.1.5 from tag v0.1.5)
ARG VERSION=latest
# Repo the release-download fallback pulls from (owner/name).
ARG GITHUB_REPO=BilalBouk/nebula-commander
# Set to 1 to download any MISSING ncclient binaries from the GitHub release for
# VERSION. Local files staged in docker/frontend/downloads/ always take precedence
# and are used offline with DOWNLOAD_BINARIES=0 (the default).
ARG DOWNLOAD_BINARIES=0

# Bake in any binaries staged locally (docker/frontend/downloads/). This is the
# primary, offline path: whatever is present here is served from the UI as-is.
# The .gitkeep keeps the dir present on a fresh clone; nginx never lists it.
RUN mkdir -p /usr/share/nginx/html/downloads
COPY docker/frontend/downloads/ /usr/share/nginx/html/downloads/

# Optionally fill in any assets not staged locally from the GitHub release, then
# make the unix CLI binaries executable (Windows-origin files lose the exec bit).
RUN cd /usr/share/nginx/html/downloads && \
    if [ "$DOWNLOAD_BINARIES" = "1" ]; then \
      base="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}"; \
      for f in ncclient-linux-amd64 ncclient-linux-arm64 ncclient-windows-amd64.exe \
               ncclient-tray-windows-amd64.exe NebulaCommander-windows-amd64.msi \
               ncclient-macos-amd64 ncclient-macos-arm64; do \
        [ -f "$f" ] || curl -fsSL -o "$f" "$base/$f"; \
      done; \
    fi && \
    rm -f README.md .gitkeep .gitignore && \
    chmod +x ncclient-linux-amd64 ncclient-linux-arm64 ncclient-macos-amd64 ncclient-macos-arm64 2>/dev/null || true

COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1
