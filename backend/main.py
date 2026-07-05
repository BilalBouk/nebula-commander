"""
Nebula Commander - self-hosted Nebula control plane.

Copyright (c) 2025 NixRTR. MIT License. See LICENSE in the repo root.
"""
import hashlib
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import init_db
from .api import (
    networks,
    nodes,
    certificates,
    auth,
    heartbeat,
    device,
    users,
    node_requests,
    access_grants,
    invitations,
    network_permissions,
    audit,
    public_config,
    dns,
)
from .middleware import RateLimitMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup."""
    logger.info("Starting %s...", settings.app_name)
    
    # Warn loudly if the unauthenticated dev-token endpoint has been explicitly enabled.
    if settings.enable_dev_token:
        logger.warning(
            "⚠️  DEV-TOKEN ENDPOINT ENABLED (NEBULA_COMMANDER_ENABLE_DEV_TOKEN=true) - "
            "anyone who can reach this server can obtain admin access WITHOUT authentication. "
            "NEVER enable this on an internet-reachable deployment."
        )
    
    await init_db()
    yield
    logger.info("Shutting down...")


VERSION = os.getenv("VERSION", "0.1.8")

# API docs (OpenAPI/Swagger) enumerate the whole API surface; only expose them in debug.
_docs_url = "/api/docs" if settings.debug else None
_redoc_url = "/api/redoc" if settings.debug else None

app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    description="Self-hosted Nebula control plane",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

# Rate limiting middleware (applied first to catch attacks early)
app.add_middleware(RateLimitMiddleware)

# Secure the session cookie whenever TLS is in play: explicitly opted in, or the public URL is
# https (production behind a TLS proxy). Local http dev keeps working (flag stays False).
_session_https_only = settings.session_https_only or (settings.public_url or "").lower().startswith("https://")

# Domain-separate the session-cookie signing key from the JWT secret so one is not trivially
# derivable from the other (audit MED-3). Still deterministic from the single configured secret.
_session_secret = hashlib.sha256(f"session-cookie:{settings.jwt_secret_key}".encode()).hexdigest()

# Session middleware (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="nebula_session",
    max_age=3600,  # 1 hour
    same_site="lax",
    https_only=_session_https_only,
)

# CORS: a wildcard origin combined with credentials is both rejected by browsers and unsafe.
# Fail closed in production; only tolerate the wildcard (without credentials) in debug.
_cors_allow_credentials = True
if "*" in settings.cors_origins:
    if not settings.debug:
        raise SystemExit(
            "Insecure CORS: NEBULA_COMMANDER_CORS_ORIGINS resolves to '*' (all origins) while "
            "credentials are enabled. Set it to an explicit comma-separated list of trusted "
            "origins (e.g. https://nebula.example.com) for any internet-reachable deployment."
        )
    logger.warning(
        "⚠️  CORS allows ALL origins (*); disabling credentialed CORS. Debug/local use only."
    )
    _cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(heartbeat.router)
app.include_router(networks.router)
app.include_router(nodes.router)
app.include_router(certificates.router)
app.include_router(device.router)
app.include_router(users.router)
app.include_router(node_requests.router)
app.include_router(access_grants.router)
app.include_router(invitations.router)
app.include_router(network_permissions.router)
app.include_router(audit.router)
app.include_router(public_config.router)
app.include_router(dns.router)


@app.get("/api")
async def root():
    """API root."""
    return {
        "name": settings.app_name,
        "version": VERSION,
        "status": "operational",
    }


@app.get("/api/health")
async def health():
    """Health check."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
