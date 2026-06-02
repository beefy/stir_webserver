"""API route handlers for stir_webserver."""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.types import (
    LoginRequest,
    MessageHistoryResponse,
    MessageOut,
    SendMessageRequest,
    SuccessResponse,
)
from app.utils import anonymize_user_id
from models.blocked import Blocked
from models.message import Message
from models.user import User

router = APIRouter()


@router.post(
    "/login",
    response_model=SuccessResponse,
    summary="Register a user",
    description="Adds a user to the users table if they don't already exist.",
)
async def login(body: LoginRequest):
    """Register a user. If the user already exists, this is a no-op."""
    existing = await User.find_one(User.user_id == body.user_id)
    if existing is None:
        user = User(user_id=body.user_id)
        await user.insert()
        return SuccessResponse(detail=f"User '{body.user_id}' registered.")
    return SuccessResponse(detail=f"User '{body.user_id}' already exists.")


@router.post(
    "/send_message",
    response_model=SuccessResponse,
    summary="Send a message to a random user",
    description=(
        "Validates the message is 255 characters or fewer, picks a random "
        "recipient from the users table (excluding the sender), and inserts "
        "the message."
    ),
)
async def send_message(body: SendMessageRequest):
    """Send a message to a random user."""
    if len(body.message_content) > 255:
        raise HTTPException(
            status_code=400,
            detail="Message must be 255 characters or fewer.",
        )

    # Find users who have blocked the sender
    blocked_entries = await Blocked.find(
        Blocked.blocked_by_user_id == body.send_user_id
    ).to_list()
    blocked_user_ids = {b.blocked_user_id for b in blocked_entries}

    # Pick a random recipient
    # (excluding the sender and anyone who blocked them)
    all_users = await User.find(
        User.user_id != body.send_user_id
    ).to_list()

    eligible = [u for u in all_users if u.user_id not in blocked_user_ids]

    if not eligible:
        raise HTTPException(
            status_code=400,
            detail="No other users available to receive the message.",
        )

    recipient = random.choice(eligible)

    message = Message(
        send_user_id=body.send_user_id,
        receive_user_id=recipient.user_id,
        message=body.message_content,
        sent_timestamp=datetime.now(timezone.utc),
        seen_timestamp=None,
        reaction_type=None,
        reported=False,
    )
    await message.insert()

    return SuccessResponse(
        detail=f"Message sent to user '{recipient.user_id}'."
    )


@router.get(
    "/message_history",
    response_model=MessageHistoryResponse,
    summary="Get message history for a user",
    description=(
        "Returns all messages where the user is the sender or receiver. "
        "The other party's user ID is deterministically anonymized using "
        "SHA-256. Results are ordered by sent_timestamp ascending."
    ),
)
async def message_history(
    user_id: str = Query(
        ...,
        description="User ID to fetch history for",
        json_schema_extra={"example": "firebase-uid-123"},
    ),
):
    """Return all messages where the user is sender or receiver."""
    messages = (
        await Message.find(
            (Message.send_user_id == user_id)
            | (Message.receive_user_id == user_id)
        )
        .sort(Message.sent_timestamp)
        .to_list()
    )

    out: list[MessageOut] = []
    for msg in messages:
        # Anonymize the "other" user
        if msg.send_user_id == user_id:
            other_id = anonymize_user_id(msg.receive_user_id)
        else:
            other_id = anonymize_user_id(msg.send_user_id)

        out.append(
            MessageOut(
                message_id=str(msg.id),
                send_user_id=(
                    user_id if msg.send_user_id == user_id else other_id
                ),
                receive_user_id=(
                    user_id if msg.receive_user_id == user_id else other_id
                ),
                message=msg.message,
                sent_timestamp=msg.sent_timestamp,
                seen_timestamp=msg.seen_timestamp,
                reaction_type=msg.reaction_type,
                reported=msg.reported,
            )
        )

    return MessageHistoryResponse(messages=out)
