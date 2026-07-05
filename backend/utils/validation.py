"""
Input validation helpers for values that flow into filesystem paths, subprocess
arguments (nebula-cert), and generated config files (dnsmasq). Centralised so the same
strict rules are applied at every boundary.
"""
import ipaddress
import re

# Nebula group/tag name. Becomes a nebula-cert -groups argument and a firewall rule key, so
# keep it to a safe label charset (no commas, whitespace, or shell/OS-significant characters).
_GROUP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


def validate_group(name: str) -> str:
    """Return the stripped group name if valid, else raise ValueError."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Group name must not be empty")
    if len(name) > 63 or not _GROUP_RE.match(name):
        raise ValueError(
            "Group name may contain only letters, digits, '.', '-' and '_', "
            "must start with a letter or digit, and be at most 63 characters"
        )
    return name


def validate_endpoint(endpoint: str) -> str:
    """
    Validate a public endpoint (host:port for Nebula static_host_map). Accepts host:port where
    host is a hostname or IPv4 and port is 1-65535. Rejects whitespace and shell/OS-significant
    characters so a bad value cannot break peer configs. Returns the stripped value.
    """
    endpoint = (endpoint or "").strip()
    if not endpoint:
        raise ValueError("Endpoint must not be empty")
    if len(endpoint) > 261 or any(c.isspace() for c in endpoint):
        raise ValueError("Invalid endpoint")
    host, sep, port = endpoint.rpartition(":")
    if not sep or not host:
        raise ValueError("Endpoint must be host:port")
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        raise ValueError("Endpoint port must be 1-65535")
    # host: IPv4 or hostname (single/multi-label). IPv6 (with brackets) is not supported here.
    try:
        ipaddress.ip_address(host)
        return endpoint
    except ValueError:
        pass
    if not _DOMAIN_RE.match(host):
        raise ValueError("Endpoint host must be a hostname or IP address")
    return endpoint


def validate_subnet_cidr(cidr: str) -> str:
    """Return the normalized network CIDR (e.g. 10.100.0.0/24) if valid, else raise ValueError."""
    cidr = (cidr or "").strip()
    if not cidr:
        raise ValueError("Subnet CIDR must not be empty")
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid subnet CIDR: {e}")
    return str(net)


# Single/multi-label hostname used as a node name. Becomes a cert CN, a nebula-cert -name
# argument, and part of on-disk cert filenames, so it must never contain path separators,
# "..", whitespace, or shell/OS-significant characters. Must start AND end with an
# alphanumeric so a name cannot end in '.', '-' or '_' (avoids "name..crt"-style filenames).
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]{0,61}[A-Za-z0-9])?$")

# DNS domain (may be multi-label, e.g. corp.example.com). No whitespace, quotes, slashes,
# or newlines — the value is written verbatim into dnsmasq config lines.
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


def validate_hostname(name: str) -> str:
    """Return the stripped hostname if valid, else raise ValueError."""
    name = (name or "").strip()
    if not name or len(name) > 63:
        raise ValueError("Hostname must be 1-63 characters")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError("Hostname must not contain '..', '/' or '\\'")
    if not _HOSTNAME_RE.match(name):
        raise ValueError(
            "Hostname may contain only letters, digits, '.', '-' and '_' "
            "and must start with a letter or digit"
        )
    return name


def is_valid_hostname(name: str) -> bool:
    try:
        validate_hostname(name)
        return True
    except ValueError:
        return False


def validate_domain(domain: str) -> str:
    """Return the stripped DNS domain if valid, else raise ValueError."""
    domain = (domain or "").strip()
    if not domain:
        raise ValueError("Domain must not be empty")
    if not _DOMAIN_RE.match(domain):
        raise ValueError("Invalid DNS domain")
    return domain


def is_valid_domain(domain: str) -> bool:
    try:
        validate_domain(domain)
        return True
    except ValueError:
        return False


def is_valid_dns_server(value: str) -> bool:
    """True if value is an IP address, optionally with a '#port' suffix (dnsmasq syntax)."""
    value = (value or "").strip()
    if not value:
        return False
    host = value
    if "#" in value:
        host, _, port = value.partition("#")
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def sanitize_dns_label(value: str) -> str:
    """Best-effort make a value safe to embed in a dnsmasq config line.

    Used as defense-in-depth for a domain that may originate from an unvalidated network
    name: strips whitespace and replaces any character outside the DNS charset with '-',
    guaranteeing the result can never inject a new config directive.
    """
    value = (value or "").strip()
    return re.sub(r"[^A-Za-z0-9.-]", "-", value) or "nebula"
