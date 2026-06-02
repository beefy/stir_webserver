import hashlib


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
