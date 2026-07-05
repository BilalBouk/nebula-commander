"""
Generate Nebula YAML config for a node from Node + Network + peer nodes.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Network, Node, NetworkGroupFirewall, RevokedCertificate

logger = logging.getLogger(__name__)

# Default paths in generated config (user places downloaded files here)
DEFAULT_PKI_CA = "/etc/nebula/ca.crt"
DEFAULT_PKI_CERT = "/etc/nebula/host.crt"
DEFAULT_PKI_KEY = "/etc/nebula/host.key"
DEFAULT_LISTEN_PORT = 4242


def _default_pki() -> dict[str, str]:
    return {
        "ca": DEFAULT_PKI_CA,
        "cert": DEFAULT_PKI_CERT,
        "key": DEFAULT_PKI_KEY,
    }


def _normalize_endpoint(endpoint: str) -> str:
    """Strip http(s):// so Nebula gets host:port only (e.g. 192.168.3.125:4242)."""
    s = endpoint.strip()
    for prefix in ("https://", "http://"):
        if s.lower().startswith(prefix):
            return s[len(prefix) :].strip()
    return s


def _default_static_host_map(hosts_with_endpoint: list[tuple[str, str]]) -> dict[str, list[str]]:
    """hosts_with_endpoint: list of (nebula_ip, public_endpoint) for lighthouses and relays."""
    return {ip: [_normalize_endpoint(endpoint)] for ip, endpoint in hosts_with_endpoint}


def _relay_section(node: Node, other_relay_ips: list[str]) -> dict[str, Any]:
    """Build relay section: am_relay, use_relays, relays (empty if this node is a relay)."""
    if node.is_relay:
        return {"am_relay": True, "use_relays": True, "relays": []}
    return {"am_relay": False, "use_relays": True, "relays": other_relay_ips}


# Interface-name patterns for OTHER overlay VPNs (and our own tun). Nebula discovers a
# host's local IPs and advertises them to the lighthouse as underlay candidates; if a node
# also runs Shieldoo/Defined/Tailscale/etc., their overlay IPs get advertised, and peers
# then try to run Nebula-over-that-VPN. That half-completes handshakes and thrashes. Exclude
# those interfaces (and our own atommesh) from the advertised local IP list.
_OVERLAY_IFACE_PATTERNS = [
    "atommesh",        # our own tun (belt-and-suspenders; Nebula usually excludes it)
    "nebula[0-9]*",    # legacy tun name
    "shd[0-9]*",       # Shieldoo
    "defined[0-9]*",   # Defined Networking
    "tailscale[0-9]*", "ts[0-9]*",  # Tailscale
    "wg[0-9]*",        # WireGuard
    "zt[a-z0-9]*",     # ZeroTier
]

# CGNAT range (100.64.0.0/10) — covers Shieldoo's 100.127.x and our own 100.100.x overlay.
# Never a valid public underlay, so never advertise it locally or dial it remotely.
_CGNAT_RANGE = "100.64.0.0/10"


def _allow_lists() -> dict[str, Any]:
    """local_allow_list / remote_allow_list that keep Nebula on the real underlay (public
    IPs + real LANs) instead of tunnelling itself over another overlay VPN on the host."""
    return {
        "local_allow_list": {
            "interfaces": {pat: False for pat in _OVERLAY_IFACE_PATTERNS},
            _CGNAT_RANGE: False,
        },
        "remote_allow_list": {
            _CGNAT_RANGE: False,
        },
    }


def _lighthouse_section(
    node: Node,
    other_lighthouse_ips: list[str],
) -> dict[str, Any]:
    """Build lighthouse section: am_lighthouse, hosts, optional interval, and allow-lists
    that exclude other overlay VPNs from underlay discovery. DNS is via ncclient dnsmasq only."""
    section: dict[str, Any] = {
        "am_lighthouse": node.is_lighthouse,
        "hosts": other_lighthouse_ips,
        **_allow_lists(),
    }
    opts = node.lighthouse_options or {}
    if node.is_lighthouse and opts.get("interval_seconds") is not None:
        section["interval"] = opts["interval_seconds"]
    return section


def _default_listen(port: int = DEFAULT_LISTEN_PORT) -> dict[str, Any]:
    return {"host": "0.0.0.0", "port": port}  # nosec B104 - Nebula node config needs all interfaces


def _endpoint_port(public_endpoint: Optional[str]) -> Optional[int]:
    """Extract the UDP port from a node's public_endpoint (host:port), or None."""
    if not public_endpoint:
        return None
    hostport = _normalize_endpoint(public_endpoint)
    # Take the port after the last colon (validate_endpoint guarantees host:port).
    _, _, tail = hostport.rpartition(":")
    try:
        p = int(tail)
        return p if 1 <= p <= 65535 else None
    except ValueError:
        return None


# Client nodes get a stable, per-node port in this range (base + node id modulo range).
# Stable (vs port 0 = new random port every restart) so the NAT mapping stays consistent
# across sessions, which makes hole-punching beat the relay-fallback race reliably;
# per-node (vs one fixed port) so multiple Nebula instances — including other meshes —
# can coexist on one host without colliding.
CLIENT_PORT_BASE = 42000
CLIENT_PORT_RANGE = 2000


def _listen_section(node: Node) -> dict[str, Any]:
    """Listen config. A node that others must reach on a fixed port — a lighthouse, a
    relay, or any node with a public_endpoint (e.g. a port-forwarded server) — listens on
    that port (from its public_endpoint, else 4242). Ordinary client nodes get a stable
    per-node port derived from their id."""
    if node.is_lighthouse or node.is_relay or node.public_endpoint:
        return _default_listen(_endpoint_port(node.public_endpoint) or DEFAULT_LISTEN_PORT)
    if node.id:
        return _default_listen(CLIENT_PORT_BASE + (node.id % CLIENT_PORT_RANGE))
    return _default_listen(0)


def _default_tun() -> dict[str, Any]:
    return {
        "dev": "atommesh",
        "drop_local_broadcast": False,
        "drop_multicast": False,
        "tx_queue": 500,
        "mtu": 1300,
        "routes": [],
    }


LOG_LEVELS = ("panic", "fatal", "error", "warning", "info", "debug")
LOG_FORMATS = ("json", "text")


def _logging_section(node: Node) -> dict[str, Any]:
    """Build logging section from node.logging_options with Nebula defaults."""
    opts = node.logging_options or {}
    level = (opts.get("level") or "info").lower()
    if level not in LOG_LEVELS:
        level = "info"
    fmt = (opts.get("format") or "text").lower()
    if fmt not in LOG_FORMATS:
        fmt = "text"
    section: dict[str, Any] = {"level": level, "format": fmt}
    if opts.get("disable_timestamp") is True:
        section["disable_timestamp"] = True
    ts_fmt = (opts.get("timestamp_format") or "").strip()
    if ts_fmt:
        section["timestamp_format"] = ts_fmt
    return section


def _default_firewall() -> dict[str, Any]:
    """Outbound allow all; inbound allow all (no rules)."""
    return {
        "conntrack": {
            "tcp_timeout": "120h",
            "udp_timeout": "3m",
            "default_timeout": "10m",
            "max_connections": 100000,
        },
        "outbound": [{"port": "any", "proto": "any", "host": "any"}],
        "inbound": [{"port": "any", "proto": "any", "host": "any"}],
    }


def _parse_port_range(port_range: str) -> list[int] | None:
    """
    Parse port_range string into list of ports. Returns None for 'any'.
    Format: "any" | "22" | "22,80-88,10000-10002"
    """
    s = (port_range or "").strip().lower()
    if not s or s == "any":
        return None
    ports: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                lo, hi = int(a.strip()), int(b.strip())
                if lo <= hi and 0 <= lo <= 65535 and 0 <= hi <= 65535:
                    ports.extend(range(lo, hi + 1))
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 0 <= p <= 65535:
                    ports.append(p)
            except ValueError:
                continue
    return ports if ports else None


def _inbound_rules_from_group_firewall(inbound_rules: list[Any]) -> list[dict[str, Any]]:
    """
    Convert defined.net-style inbound rules to Nebula format.
    New shape: allowed_group, protocol, port_range, description.
    Legacy shape: group, proto, port (one port or "any") - converted for backward compat.
    Expands port_range into one Nebula rule per port; group = allowed_group, proto = protocol.
    """
    nebula_rules: list[dict[str, Any]] = []
    for r in inbound_rules or []:
        if not isinstance(r, dict):
            continue
        allowed_group = (r.get("allowed_group") or r.get("group") or "").strip()
        if not allowed_group:
            continue
        protocol = (r.get("protocol") or r.get("proto") or "any").strip().lower()
        if protocol not in ("any", "tcp", "udp", "icmp"):
            protocol = "any"
        port_range = (r.get("port_range") or str(r.get("port", "any")).strip() or "any").strip()
        ports = _parse_port_range(port_range)
        if ports is None:
            nebula_rules.append({"port": "any", "proto": protocol, "group": allowed_group})
        else:
            for port in ports:
                nebula_rules.append({"port": port, "proto": protocol, "group": allowed_group})
    return nebula_rules


def _firewall_section(
    network: Network,
    node: Node,
    group_firewalls: list[Any],
) -> dict[str, Any]:
    """
    Defined.net style: no network firewall. Outbound allow all.
    Inbound deny by default; allow only rules from the node's single group.
    Node has one group (node.groups[0]); that group's inbound_rules define who can reach this node.
    """
    section: dict[str, Any] = {
        "conntrack": {
            "tcp_timeout": "120h",
            "udp_timeout": "3m",
            "default_timeout": "10m",
            "max_connections": 100000,
        },
        "outbound": [{"port": "any", "proto": "any", "host": "any"}],
    }
    node_group = (node.groups or [None])[0] if (node.groups and len(node.groups) > 0) else None
    group_by_name = {gf.group_name: gf for gf in group_firewalls if getattr(gf, "group_name", None)}
    gf = group_by_name.get(node_group) if node_group else None
    inbound_rules_raw = getattr(gf, "inbound_rules", None) or [] if gf else []

    if not inbound_rules_raw:
        section["inbound"] = [{"port": "any", "proto": "any", "host": "any"}]
        return section

    section["inbound_action"] = "drop"
    section["inbound"] = _inbound_rules_from_group_firewall(inbound_rules_raw)
    if not section["inbound"]:
        section["inbound"] = [{"port": "any", "proto": "any", "host": "any"}]
    return section


def _punchy_section(node: Node) -> dict[str, Any]:
    """Build punchy section. Nested format: punch, respond, optional delay/respond_delay."""
    opts = node.punchy_options or {}
    section: dict[str, Any] = {
        "punch": True,
        "respond": opts.get("respond", True),
    }
    if opts.get("delay"):
        section["delay"] = opts["delay"]
    if opts.get("respond_delay"):
        section["respond_delay"] = opts["respond_delay"]
    return section


def build_config(
    node: Node,
    network: Network,
    peer_nodes: list[Node],
    group_firewalls: list[Any],
    inline_pki: Optional[tuple[str, str, str]] = None,
    blocklist: Optional[list[str]] = None,
) -> str:
    """
    Build Nebula YAML config for the given node.
    peer_nodes: all other nodes in the same network (for lighthouses list and static_host_map).
    inline_pki: optional (ca_pem, cert_pem, key_pem) to embed certs in config (OS-independent; no file paths).
    blocklist: optional list of revoked cert fingerprints to publish as pki.blocklist so every
      node refuses the revoked certs (Nebula's only revocation mechanism).
    """
    # Any node with a public_endpoint is directly reachable there, so advertise it in
    # static_host_map. This lets peers connect DIRECTLY (not just via the relay) to a
    # reachable server node (e.g. a port-forwarded office server or PACS), which is far
    # faster and more stable than relaying every packet through the lighthouse.
    hosts_with_endpoint = [
        (n.ip_address, n.public_endpoint)
        for n in peer_nodes
        if n.public_endpoint and n.ip_address
    ]
    lighthouses_with_endpoint = [
        (n.ip_address, n.public_endpoint)
        for n in peer_nodes
        if n.is_lighthouse and n.public_endpoint and n.ip_address
    ]
    other_lighthouse_ips = [ip for ip, _ in lighthouses_with_endpoint if ip != node.ip_address]
    other_relay_ips = [
        n.ip_address for n in peer_nodes
        if n.is_relay and n.ip_address and n.ip_address != node.ip_address
    ]

    if inline_pki is not None:
        ca_pem, cert_pem, key_pem = inline_pki
        pki_section: dict[str, Any] = {
            "ca": ca_pem.rstrip() + "\n",
            "cert": cert_pem.rstrip() + "\n",
            "key": key_pem.rstrip() + "\n",
        }
    else:
        pki_section = _default_pki()

    # Publish revoked (non-expired) cert fingerprints so every node rejects them. This is
    # Nebula's only working revocation path; without it a revoked node keeps mesh access
    # until its cert naturally expires.
    if blocklist:
        pki_section["blocklist"] = list(blocklist)

    config: dict[str, Any] = {
        "pki": pki_section,
        "static_host_map": _default_static_host_map(hosts_with_endpoint) if hosts_with_endpoint else {},
        "lighthouse": _lighthouse_section(node, other_lighthouse_ips),
        "relay": _relay_section(node, other_relay_ips),
        "listen": _listen_section(node),
        "punchy": _punchy_section(node),
        "tun": _default_tun(),
        "logging": _logging_section(node),
        "firewall": _firewall_section(network, node, group_firewalls),
    }

    # Remove empty static_host_map so Nebula doesn't complain
    if not config["static_host_map"]:
        del config["static_host_map"]

    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


async def generate_config_for_node(
    session: AsyncSession,
    node_id: int,
    inline_pki: Optional[tuple[str, str, str]] = None,
) -> Optional[str]:
    """
    Load node + network + peers and return generated YAML config, or None if node not found.
    inline_pki: optional (ca_pem, cert_pem, key_pem) to embed in config (no file paths).
    """
    result = await session.execute(
        select(Node).where(Node.id == node_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        return None

    result = await session.execute(
        select(Network).where(Network.id == node.network_id)
    )
    network = result.scalar_one_or_none()
    if not network:
        return None

    result = await session.execute(
        select(Node).where(Node.network_id == node.network_id)
    )
    all_nodes = list(result.scalars().all())
    peer_nodes = [n for n in all_nodes if n.id != node.id]

    result = await session.execute(
        select(NetworkGroupFirewall).where(NetworkGroupFirewall.network_id == network.id)
    )
    group_firewalls = list(result.scalars().all())

    # Revoked-but-not-yet-expired cert fingerprints for this network -> pki.blocklist.
    # Sourced from the network-scoped revoked_certificates table (indexed on network_id) so
    # revocation survives node/cert deletion and this hot-path poll query stays a single
    # indexed lookup.
    result = await session.execute(
        select(RevokedCertificate.fingerprint).where(
            RevokedCertificate.network_id == node.network_id,
            RevokedCertificate.expires_at > datetime.utcnow(),
        )
    )
    blocklist = [row[0] for row in result.all()]

    return build_config(
        node, network, peer_nodes, group_firewalls, inline_pki=inline_pki, blocklist=blocklist
    )
