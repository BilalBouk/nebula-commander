"""
Audit logging for sensitive actions. Entries are visible to system admins only.
"""
from __future__ import annotations

import ipaddress
import json
from functools import lru_cache
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import AuditLog


@lru_cache(maxsize=8)
def _parse_trusted_cidrs(cidrs: tuple[str, ...]) -> tuple:
    nets = []
    for c in cidrs:
        try:
            nets.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def _peer_is_trusted_proxy(peer: str, cidrs: tuple[str, ...]) -> bool:
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(ip in net for net in _parse_trusted_cidrs(cidrs))


def get_client_ip(request: Request) -> str:
    """
    Get the client IP, honoring X-Forwarded-For only when the direct TCP peer is a trusted
    proxy AND only for the configured number of proxy hops. Each trusted proxy appends the
    address it received the connection from, so the real client is the entry
    `trusted_proxy_count` from the right — NOT the leftmost, which is fully attacker-controlled.

    Crucially, XFF is trusted only when `request.client.host` is inside `trusted_proxies`: a
    client that reaches the backend directly (e.g. a sibling container, or any deploy without
    the bundled proxy) cannot spoof its source IP — and thus cannot forge a fresh rate-limit
    bucket or a fake audit-log IP — by sending its own X-Forwarded-For. With trusted_proxy_count=0
    or an untrusted peer, XFF is ignored and the real peer address is used.
    """
    from ..config import settings

    peer = request.client.host if request.client else ""
    n = settings.trusted_proxy_count
    if n and n > 0 and peer and _peer_is_trusted_proxy(peer, tuple(settings.trusted_proxies)):
        parts = [p.strip() for p in (request.headers.get("X-Forwarded-For") or "").split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return peer


async def log_audit(
    session: AsyncSession,
    action: str,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    result: str = "success",
    actor_user_id: Optional[int] = None,
    actor_identifier: Optional[str] = None,
    details: Optional[str] | Optional[dict] = None,
    client_ip: Optional[str] = None,
) -> None:
    """
    Append one audit log entry. Does not commit; caller must commit the session.
    """
    details_str: Optional[str] = None
    if details is not None:
        details_str = json.dumps(details) if isinstance(details, dict) else details

    entry = AuditLog(
        action=action,
        actor_user_id=actor_user_id,
        actor_identifier=actor_identifier,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        details=details_str,
        client_ip=client_ip,
    )
    session.add(entry)
