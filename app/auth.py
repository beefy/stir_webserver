"""
Authentication utility for stir_webserver.

Validates Firebase ID tokens by calling the auth microservice's /api/verify
endpoint. Returns the authenticated user's Firebase UID and email verification
status.
"""

import os

import httpx

AUTH_SERVICE_URL = os.getenv(
    "AUTH_SERVICE_URL",
    "http://localhost:3001",
)


class AuthError(Exception):
    """Raised when token validation fails."""

    def __init__(self, detail: str, status_code: int = 401):
        self.detail = detail
        self.status_code = status_code


async def verify_token(authorization: str | None) -> tuple[str, bool]:
    """Validate a Firebase ID token via the auth microservice.

    Args:
        authorization: The value of the Authorization header
                       (e.g. "Bearer eyJhbGciOiJSUzI1NiIs...").

    Returns:
        A tuple of (uid, email_verified).

    Raises:
        AuthError: If the token is missing, invalid, or the auth service
                   is unavailable.
    """
    if not authorization:
        raise AuthError("Access token required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid authorization header format")

    token = parts[1]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/api/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError:
            raise AuthError(
                "Authentication service unavailable",
                status_code=503,
            )

    if response.status_code == 401:
        raise AuthError("Access token required")
    elif response.status_code == 403:
        raise AuthError("Invalid or expired token")
    elif response.status_code != 200:
        raise AuthError(
            "Authentication service unavailable",
            status_code=503,
        )

    data = response.json()
    user = data["user"]
    return user["uid"], user.get("emailVerified", False)


async def get_firebase_user(authorization: str | None) -> dict:
    """Fetch the full Firebase user record from the auth microservice.

    Args:
        authorization: The value of the Authorization header
                       (e.g. "Bearer eyJhbGciOiJSUzI1NiIs...").

    Returns:
        The full Firebase user object as a dict.

    Raises:
        AuthError: If the token is missing, invalid, or the auth service
                   is unavailable.
    """
    if not authorization:
        raise AuthError("Access token required")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid authorization header format")

    token = parts[1]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{AUTH_SERVICE_URL}/api/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except httpx.RequestError:
            raise AuthError(
                "Authentication service unavailable",
                status_code=503,
            )

    if response.status_code == 401:
        raise AuthError("Access token required")
    elif response.status_code == 403:
        raise AuthError("Invalid or expired token")
    elif response.status_code != 200:
        raise AuthError(
            "Authentication service unavailable",
            status_code=503,
        )

    data = response.json()
    return data["user"]
