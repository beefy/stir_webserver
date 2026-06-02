"""API route handlers for stir_webserver."""

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.types import (
    BlockedUserEntry,
    BlockListRequest,
    BlockListResponse,
    BlockUserRequest,
    LoginRequest,
    MessageHistoryResponse,
    MessageOut,
    ReactToMessageRequest,
    ReportMessageRequest,
    SendMessageRequest,
    SuccessResponse,
    UnblockUserRequest,
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
    # (the sender should not be able to message them)
    blocked_entries = await Blocked.find(
        Blocked.blocked_user_id == body.send_user_id
    ).to_list()
    blocked_by_user_ids = {b.blocked_by_user_id for b in blocked_entries}

    # Pick a random recipient
    # (excluding the sender and anyone who has blocked the sender)
    all_users = await User.find(
        User.user_id != body.send_user_id
    ).to_list()

    eligible = [u for u in all_users if u.user_id not in blocked_by_user_ids]

    if not eligible:
        raise HTTPException(
            status_code=400,
            detail="No other users available to receive the message.",
        )

    recipient = random.choice(eligible)

    message = Message(
        message_id=str(uuid.uuid4()),
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
        detail="Message sent."
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
            {"$or": [
                {"send_user_id": user_id},
                {"receive_user_id": user_id},
            ]}
        )
        .sort(Message.sent_timestamp)
        .to_list()
    )

    # Mark messages as seen where the requesting user is the receiver
    now = datetime.now(timezone.utc)
    for msg in messages:
        if msg.receive_user_id == user_id and msg.seen_timestamp is None:
            msg.seen_timestamp = now
            await msg.save()

    out: list[MessageOut] = []
    for msg in messages:
        # Anonymize the "other" user
        if msg.send_user_id == user_id:
            other_id = anonymize_user_id(msg.receive_user_id)
        else:
            other_id = anonymize_user_id(msg.send_user_id)

        out.append(
            MessageOut(
                message_id=msg.message_id,
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


@router.post(
    "/block_user",
    response_model=SuccessResponse,
    summary="Block a user",
    description=(
        "Adds a record to the blocked table. If the block record already "
        "exists, this is a no-op."
    ),
)
async def block_user(body: BlockUserRequest):
    """Block the sender of a message. If already blocked, this is a no-op."""
    # Look up the message to find the sender
    message = await Message.find_one(Message.message_id == body.message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    blocked_user_id = message.send_user_id

    existing = await Blocked.find_one(
        Blocked.blocked_by_user_id == body.blocked_by_user_id,
        Blocked.blocked_user_id == blocked_user_id,
    )
    if existing is None:
        entry = Blocked(
            blocked_user_id=blocked_user_id,
            blocked_by_user_id=body.blocked_by_user_id,
            blocked_timestamp=datetime.now(timezone.utc),
        )
        await entry.insert()
        return SuccessResponse(
            detail="User blocked."
        )
    return SuccessResponse(
        detail="User is already blocked."
    )


@router.post(
    "/unblock_user",
    response_model=SuccessResponse,
    summary="Unblock a user",
    description=(
        "Removes the block record from the blocked table if it exists. "
        "If no such block exists, this is a no-op."
    ),
)
async def unblock_user(body: UnblockUserRequest):
    """Unblock a user. If not currently blocked, this is a no-op."""
    existing = await Blocked.find_one(
        Blocked.blocked_by_user_id == body.blocked_by_user_id,
        Blocked.blocked_user_id == body.blocked_user_id,
    )
    if existing is not None:
        await existing.delete()
        return SuccessResponse(
            detail=f"User '{body.blocked_user_id}' unblocked."
        )
    return SuccessResponse(
        detail=f"User '{body.blocked_user_id}' was not blocked."
    )


@router.post(
    "/block_list",
    response_model=BlockListResponse,
    summary="Get block list for a user",
    description=(
        "Returns a list of all user IDs that the specified user has "
        "blocked. The returned user IDs are deterministically anonymized "
        "using SHA-256."
    ),
)
async def block_list(body: BlockListRequest):
    """Return all blocked users with their messages to the blocker."""
    entries = await Blocked.find(
        Blocked.blocked_by_user_id == body.blocked_by_user_id
    ).to_list()

    blocked_users: list[BlockedUserEntry] = []
    for entry in entries:
        anonymized_id = anonymize_user_id(entry.blocked_user_id)

        # Find messages sent by the blocked user to the blocker
        messages = (
            await Message.find(
                Message.send_user_id == entry.blocked_user_id,
                Message.receive_user_id == body.blocked_by_user_id,
            )
            .sort(Message.sent_timestamp)
            .to_list()
        )

        message_outs = [
            MessageOut(
                message_id=msg.message_id,
                send_user_id=anonymized_id,
                receive_user_id=body.blocked_by_user_id,
                message=msg.message,
                sent_timestamp=msg.sent_timestamp,
                seen_timestamp=msg.seen_timestamp,
                reaction_type=msg.reaction_type,
                reported=msg.reported,
            )
            for msg in messages
        ]

        blocked_users.append(
            BlockedUserEntry(
                blocked_user_id=anonymized_id,
                messages=message_outs,
            )
        )

    return BlockListResponse(blocked_users=blocked_users)


@router.post(
    "/react_to_message",
    response_model=SuccessResponse,
    summary="React to a message",
    description=(
        "Sets the reaction on a message. Accepted reaction values are "
        "'up', 'down', or null (to clear the reaction)."
    ),
)
async def react_to_message(body: ReactToMessageRequest):
    """Set or clear a reaction on a message."""
    VALID_REACTIONS = {"up", "down", None}

    if body.reaction_content not in VALID_REACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid reaction '{body.reaction_content}'. "
                f"Accepted values: 'up', 'down', or null."
            ),
        )

    message = await Message.find_one(Message.message_id == body.message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    message.reaction_type = body.reaction_content
    await message.save()

    return SuccessResponse(
        detail=(
            f"Reaction set to '{body.reaction_content}' "
            f"on message {body.message_id}."
        )
    )


@router.post(
    "/report_message",
    response_model=SuccessResponse,
    summary="Report a message",
    description="Sets the reported flag to true for the specified message.",
)
async def report_message(body: ReportMessageRequest):
    """Mark a message as reported."""
    message = await Message.find_one(Message.message_id == body.message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    message.reported = True
    await message.save()

    return SuccessResponse(
        detail=f"Message {body.message_id} reported."
    )
