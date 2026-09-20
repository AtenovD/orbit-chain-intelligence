from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from orchestrator.config import get_settings


def validate_outbound_url(value: str) -> str:
    """Reject SSRF targets in production, including private DNS answers."""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP(S) endpoints are supported")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in an endpoint URL")
    if get_settings().app_env != "production":
        return value
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Private network endpoints are not allowed in production")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise ValueError("Endpoint hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Private, loopback, link-local and reserved endpoints are not allowed")
    return value
