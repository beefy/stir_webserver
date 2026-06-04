import hashlib

from fastapi import Header

from app.auth import AuthError, verify_token


async def get_current_user(
    authorization: str | None = Header(None),
) -> str:
    """Validate the Firebase token and return the authenticated user's UID."""
    try:
        return await verify_token(authorization)
    except AuthError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        )


def anonymize_user_id(user_id: str) -> str:
    """Deterministically anonymize a user ID using SHA-256.

    Given the same input, this function always returns the same output,
    making it suitable for consistent anonymization across requests.

    Args:
        user_id: The original user ID to anonymize.

    Returns:
        A truncated SHA-256 hex digest (first 16 characters) prefixed
        with "anon_".
    """
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"anon_{digest[:16]}"
