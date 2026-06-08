"""
IP-based geolocation blocking middleware.

Uses ip-api.com (free tier, no API key required) to look up the client's
IP address and block requests from restricted US states and countries
as defined in IP_BLOCKING.md.

Rate limit note: ip-api.com free tier allows 45 requests per minute.
A simple in-memory cache is used to avoid hitting this limit.
"""

import os
import time
from collections import OrderedDict

import httpx
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# Restricted locations (from IP_BLOCKING.md)
# ---------------------------------------------------------------------------

RESTRICTED_US_STATES: set[str] = {
    "MS",  # Mississippi
    "SD",  # South Dakota
    "WY",  # Wyoming
    "HI",  # Hawaii
    "TX",  # Texas
    "TN",  # Tennessee
    "VA",  # Virginia
    "KS",  # Kansas
}

RESTRICTED_COUNTRIES: set[str] = {
    "AU",  # Australia
    "FR",  # France
    "PT",  # Portugal
    "IT",  # Italy
    "GR",  # Greece
}

# ---------------------------------------------------------------------------
# In-memory LRU cache for IP geolocation results
# ---------------------------------------------------------------------------

IP_CACHE_MAX_SIZE = 5000
_ip_cache: OrderedDict[str, tuple[str | None, str | None, float]] = (
    OrderedDict()
)
"""Maps IP -> (country_code, state_code, cached_at_timestamp)."""


def _get_cached(ip: str) -> tuple[str | None, str | None] | None:
    """Return (country_code, state_code) from cache, or None if not cached."""
    entry = _ip_cache.get(ip)
    if entry is None:
        return None
    country_code, state_code, cached_at = entry
    # Cache for 1 hour (3600 seconds)
    if time.time() - cached_at > 3600:
        del _ip_cache[ip]
        return None
    # Move to end (most recently used)
    _ip_cache.move_to_end(ip)
    return country_code, state_code


def _set_cache(
    ip: str, country_code: str | None, state_code: str | None
) -> None:
    """Store geolocation result in cache."""
    if len(_ip_cache) >= IP_CACHE_MAX_SIZE:
        _ip_cache.popitem(last=False)  # Remove oldest (LRU)
    _ip_cache[ip] = (country_code, state_code, time.time())


# ---------------------------------------------------------------------------
# Geolocation lookup
# ---------------------------------------------------------------------------

IP_API_URL = "http://ip-api.com/json/"


class IPLookupError(Exception):
    """Raised when IP geolocation lookup fails."""


async def _lookup_ip(
    ip: str,
) -> tuple[str | None, str | None, bool]:
    """Look up an IP address via ip-api.com.

    Returns:
        A tuple of (country_code, state_code, is_proxy). ``is_proxy`` is
        ``True`` if the IP is a VPN, proxy, or hosting provider. Either
        country/state may be None if the IP is private.

    Raises:
        IPLookupError: If the geolocation service is unavailable, returns
                       a non-200 status, or a request error occurs.
    """
    # Don't look up private / loopback IPs
    if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith(
        ("10.", "172.16.", "192.168.")
    ):
        return None, None, False

    cached = _get_cached(ip)
    if cached is not None:
        country_code, state_code = cached
        return country_code, state_code, False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{IP_API_URL}{ip}",
                params={"fields": "countryCode,region,proxy"},
                timeout=5.0,
            )
    except (httpx.RequestError, httpx.TimeoutException):
        raise IPLookupError("IP geolocation service unavailable")

    if response.status_code != 200:
        raise IPLookupError(
            f"IP geolocation service returned status {response.status_code}"
        )

    data = response.json()
    country_code: str | None = data.get("countryCode") or None
    state_code: str | None = data.get("region") or None
    is_proxy: bool = data.get("proxy", False)

    _set_cache(ip, country_code, state_code)
    return country_code, state_code, is_proxy


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class IPBlockingMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that blocks requests from restricted locations.

    The middleware is enabled when the ``IP_BLOCKING_ENABLED`` environment
    variable is set to ``"true"`` (case-insensitive).  When disabled, all
    requests pass through without geolocation checks.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Enabled by default; set IP_BLOCKING_ENABLED=false to disable
        if os.getenv("IP_BLOCKING_ENABLED", "true").lower() == "false":
            return await call_next(request)

        # Extract client IP from X-Forwarded-For or fall back to RemoteAddr
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else None

        if client_ip is None:
            return await call_next(request)

        try:
            country_code, state_code, is_proxy = await _lookup_ip(client_ip)
        except IPLookupError:
            # Fail closed: block access if geolocation is unavailable
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Access is not available at this time. "
                        "Please try again later."
                    ),
                },
            )

        # Block VPN / proxy usage (enabled by default; set BLOCK_VPN=false
        # to disable)
        if is_proxy and os.getenv("BLOCK_VPN", "true").lower() != "false":
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Access is not available from VPN or proxy "
                        "connections."
                    ),
                },
            )

        # Check country-level restrictions
        if country_code and country_code in RESTRICTED_COUNTRIES:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Access is not available from your country "
                        "due to geographic restrictions."
                    ),
                },
            )

        # Check US state-level restrictions
        if country_code == "US" and state_code:
            if state_code.upper() in RESTRICTED_US_STATES:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Access is not available from your state "
                            "due to geographic restrictions."
                        ),
                    },
                )

        return await call_next(request)
