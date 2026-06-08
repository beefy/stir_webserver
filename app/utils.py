import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import Header

from app.auth import AuthError, verify_token
from models.moderation import Moderation
from models.message import Message
from models.user import User

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


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


async def run_moderation(message_id: str, message_content: str) -> None:
    """Call DeepSeek to moderate a message and record the result.

    This is intended to be run as a fire-and-forget background task so
    the original API response is not delayed.
    """
    if not DEEPSEEK_API_KEY:
        # No API key configured — record a null-action moderation
        moderation = Moderation(
            moderation_id=str(uuid.uuid4()),
            message_id=message_id,
            moderation_action=None,
            moderation_datetime=datetime.now(timezone.utc),
        )
        await moderation.insert()
        return

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a content moderation assistant. "
                                "Respond only in JSON with either "
                                '{"moderation_action": "ban"} or '
                                '{"moderation_action": "dismiss"}.'
                                'Respond with {"moderation_action": "ban"} if the message content contains hate speech, harassment, explicit content, calls for violence, or anything else that you think would qualify banning a user.'
                                'Otherwise, respond with {"moderation_action": "dismiss"}.'
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Moderate this message: {message_content}"
                            ),
                        },
                    ],
                    "max_tokens": 50,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            parsed = json.loads(content)
            action = parsed.get("moderation_action")
            if action not in ("ban", "dismiss"):
                action = None
    except Exception:
        # If DeepSeek is unreachable or response is not valid JSON,
        # set action to None
        action = None

    moderation = Moderation(
        moderation_id=str(uuid.uuid4()),
        message_id=message_id,
        moderation_action=action,
        moderation_datetime=datetime.now(timezone.utc),
    )
    await moderation.insert()

    # If the action is "ban", shadow ban the sender
    if action == "ban":
        message = await Message.find_one(Message.message_id == message_id)
        if message is not None:
            user = await User.find_one(User.user_id == message.send_user_id)
            if user is not None:
                user.shadow_banned = True
                await user.save()
