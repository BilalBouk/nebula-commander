"""
Audit logging for sensitive actions. Entries are visible to system admins only.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import AuditLog


def get_client_ip(request: Request) -> str:
    """
    Get the client IP, honoring X-Forwarded-For only for the configured number of trusted
    proxies. Each trusted proxy appends the address it received the connection from, so the
    real client is the entry `trusted_proxy_count` from the right — NOT the leftmost, which is
    fully attacker-controlled. With trusted_proxy_count=0, XFF is ignored entirely (direct
    exposure). This prevents spoofing the logged/rate-limited source IP via a forged header.
    """
    from ..config import settings

    n = settings.trusted_proxy_count
    if n and n > 0:
        parts = [p.strip() for p in (request.headers.get("X-Forwarded-For") or "").split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    if request.client:
        return request.client.host
    return ""


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
