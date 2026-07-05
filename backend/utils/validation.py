"""
Input validation helpers for values that flow into filesystem paths, subprocess
arguments (nebula-cert), and generated config files (dnsmasq). Centralised so the same
strict rules are applied at every boundary.
"""
import ipaddress
import re

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
