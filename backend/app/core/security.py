import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",
}
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class UnsafeURLError(ValueError):
    """Raised when a URL violates scheme or SSRF network safety policies."""


def validate_url_syntax(raw_url: str) -> str:
    """Validate that a URL is well-formed http/https with no credentials or local hostnames."""
    if not isinstance(raw_url, str):
        raise UnsafeURLError("URL must be a string.")
    cleaned = raw_url.strip()
    if not cleaned:
        raise UnsafeURLError("URL cannot be empty.")
    if len(cleaned) > 2048:
        raise UnsafeURLError("URL exceeds maximum length (2048 characters).")

    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"Unsupported URL scheme '{scheme or 'none'}'. Only http/https allowed."
        )
    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs with embedded credentials are not permitted.")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise UnsafeURLError("URL is missing a valid hostname.")
    if (
        hostname in BLOCKED_HOSTNAMES
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".localhost")
    ):
        raise UnsafeURLError(f"Hostname '{hostname}' is not permitted.")

    # Direct IP literal check
    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None
    if ip_obj is not None and not is_ip_public(ip_obj):
        raise UnsafeURLError(f"IP address '{hostname}' is in a restricted range.")

    return cleaned


def is_ip_public(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only when IP is globally routable public unicast."""
    if ip_obj.is_loopback:
        return False
    if ip_obj.is_private:
        return False
    if ip_obj.is_link_local:
        return False
    if ip_obj.is_multicast:
        return False
    if ip_obj.is_reserved:
        return False
    if ip_obj.is_unspecified:
        return False
    if not ip_obj.is_global:
        return False
    if isinstance(ip_obj, ipaddress.IPv4Address) and str(ip_obj) == "169.254.169.254":
        return False
    return True


async def validate_url_ssrf_safe(raw_url: str) -> str:
    """Validate URL syntax and resolve DNS to ensure no target IP is private/loopback/reserved."""
    cleaned = validate_url_syntax(raw_url)
    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        ipaddress.ip_address(hostname)
        return cleaned
    except ValueError:
        pass

    try:
        addr_info = await asyncio.to_thread(
            socket.getaddrinfo, hostname, port, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname '{hostname}'.") from exc

    if not addr_info:
        raise UnsafeURLError(f"No network addresses resolved for '{hostname}'.")

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = str(sockaddr[0]).split("%")[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise UnsafeURLError(f"Invalid resolved address '{ip_str}'.") from exc
        if not is_ip_public(ip_obj):
            raise UnsafeURLError(
                f"Hostname '{hostname}' resolves to non-public address '{ip_str}'."
            )
    return cleaned


def canonicalize_url(raw_url: str) -> str:
    """Normalize URL for deduplication while dropping tracking query parameters."""
    parsed = urlparse(raw_url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    filtered_qs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    query = urlencode(sorted(filtered_qs))
    return urlunparse((scheme, netloc, path, "", query, ""))


def sanitize_untrusted_text(text: str, max_chars: int = 3500) -> str:
    """Strip unsafe control characters and cap excerpt length for untrusted web text."""
    cleaned = _CONTROL_CHARS.sub(" ", text or "")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_chars:
        return cleaned[: max_chars - 3].rstrip() + "..."
    return cleaned
