"""API route handlers for stir_webserver."""

import random
import uuid
from datetime import datetime, timezone

import math

from fastapi import APIRouter, Depends, HTTPException, Header, Query

from app.auth import AuthError, verify_token
from app.types import (
    BlockedUserEntry,
    BlockListResponse,
    BlockUserRequest,
    ForwardMessageRequest,
    KarmaCountResponse,
    MessageHistoryResponse,
    MessageOut,
    PaginationInfo,
    ReactToMessageRequest,
    ReportMessageRequest,
    SendMessageRequest,
    SuccessResponse,
    UnblockUserRequest,
    UnreadMessagesResponse,
)
from app.utils import anonymize_user_id
from models.blocked import Blocked
from models.message import Message
from models.message_lineage import MessageLineage
from models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency: extract authenticated user ID from the Authorization header
# ---------------------------------------------------------------------------


async def get_current_user(
    authorization: str | None = Header(None),
) -> str:
    """Validate the Firebase token and return the authenticated user's UID."""
    try:
        return await verify_token(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _send_message_to_user(
    sender_user_id: str,
    message_content: str,
    recipient_user_id: str,
) -> Message:
    """Create and insert a message.

    This is the core send logic used by both ``/send_message`` and
    ``/forward_message``.  It does **not** perform rate-limiting or
    eligibility checks — the caller is responsible for those.
    """
    message = Message(
        message_id=str(uuid.uuid4()),
        send_user_id=sender_user_id,
        receive_user_id=recipient_user_id,
        message=message_content,
        sent_timestamp=datetime.now(timezone.utc),
        seen_timestamp=None,
        reaction_type=None,
        reported=False,
    )
    await message.insert()
    return message


async def _get_forward_stats(
    message_id: str,
    original_sender_user_id: str,
) -> tuple[int, int]:
    """Return ``(forward_count, total_karma)`` for a message.

    *forward_count* is the number of times this message (as the original)
    has been forwarded.  *total_karma* is the sum of karma from the original
    message plus all forwarded copies.
    """
    # Count forwards where this message is the original
    forward_count = await MessageLineage.find(
        MessageLineage.original_message_id == message_id,
    ).count()

    # Collect all message IDs in the forward chain (original + clones)
    lineage_records = await MessageLineage.find(
        MessageLineage.original_message_id == message_id,
    ).to_list()
    all_message_ids = [message_id] + [
        r.cloned_message_id for r in lineage_records
    ]

    # Sum karma across all copies
    total_karma = 0
    for mid in all_message_ids:
        msg = await Message.find_one(Message.message_id == mid)
        if msg and msg.reaction_type == "up":
            total_karma += 1
        elif msg and msg.reaction_type == "down":
            total_karma -= 1

    return forward_count, total_karma


async def _has_user_forwarded_message(
    user_id: str,
    original_message_id: str,
) -> bool:
    """Check if *user_id* has already forwarded the given original message.

    Looks for a lineage record where the original_message_id matches and
    the cloned message was sent by *user_id*.
    """
    lineage_records = await MessageLineage.find(
        MessageLineage.original_message_id == original_message_id,
    ).to_list()

    for record in lineage_records:
        cloned_msg = await Message.find_one(
            Message.message_id == record.cloned_message_id
        )
        if cloned_msg and cloned_msg.send_user_id == user_id:
            return True

    return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=SuccessResponse,
    summary="Register a user",
    description=(
        "Registers the authenticated user if they don't already exist. "
        "The user ID is extracted from the Firebase auth token."
    ),
)
async def login(
    current_user: str = Depends(get_current_user),
):
    """Register the authenticated user. If already exists, this is a no-op."""
    existing = await User.find_one(User.user_id == current_user)
    if existing is None:
        user = User(user_id=current_user)
        await user.insert()
        return SuccessResponse(detail=f"User '{current_user}' registered.")
    return SuccessResponse(detail=f"User '{current_user}' already exists.")


@router.post(
    "/send_message",
    response_model=SuccessResponse,
    summary="Send a message to a random user",
    description=(
        "Validates the message is 255 characters or fewer, picks a random "
        "recipient from the users table (excluding the sender), and inserts "
        "the message. The sender is determined from the auth token."
    ),
)
async def send_message(
    body: SendMessageRequest,
    current_user: str = Depends(get_current_user),
):
    """Send a message to a random user."""
    if len(body.message_content) > 255:
        raise HTTPException(
            status_code=400,
            detail="Message must be 255 characters or fewer.",
        )

    # Rate limit: check if the user sent a message in the last 5 seconds
    last_message = (
        await Message.find(Message.send_user_id == current_user)
        .sort(-Message.sent_timestamp)
        .limit(1)
        .to_list()
    )
    if last_message:
        # sent_timestamp is stored as offset-naive UTC in MongoDB
        elapsed = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            - last_message[0].sent_timestamp
        ).total_seconds()
        if elapsed < 5:
            raise HTTPException(
                status_code=429,
                detail=(
                    "You are sending messages too fast. "
                    "Please wait before sending another message."
                ),
            )

    # Find users who have blocked the sender
    # (the sender should not be able to message them)
    blocked_entries = await Blocked.find(
        Blocked.blocked_user_id == current_user
    ).to_list()
    blocked_by_user_ids = {b.blocked_by_user_id for b in blocked_entries}

    # Pick a random recipient
    # (excluding the sender and anyone who has blocked the sender)
    all_users = await User.find(
        User.user_id != current_user,
    ).to_list()

    eligible = [u for u in all_users if u.user_id not in blocked_by_user_ids]

    if not eligible:
        raise HTTPException(
            status_code=400,
            detail="No other users available to receive the message.",
        )

    recipient = random.choice(eligible)

    await _send_message_to_user(
        sender_user_id=current_user,
        message_content=body.message_content,
        recipient_user_id=recipient.user_id,
    )

    return SuccessResponse(
        detail="Message sent."
    )


@router.post(
    "/forward_message",
    response_model=SuccessResponse,
    summary="Forward a message to a random user",
    description=(
        "Forwards the specified message to a random eligible recipient. "
        "The authenticated user must be the receiver of the original "
        "message. The forwarded message content is copied from the "
        "original, and a message_lineage record is created to track "
        "the forward chain."
    ),
)
async def forward_message(
    body: ForwardMessageRequest,
    current_user: str = Depends(get_current_user),
):
    """Forward a received message to a random user."""
    # Look up the original message
    original_message = await Message.find_one(
        Message.message_id == body.message_id
    )
    if original_message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    # Only the receiver of the message can forward it
    if original_message.receive_user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="You can only forward messages you received.",
        )

    # Determine the original message ID for the lineage chain.
    # If the message being forwarded was itself a forward, use the
    # original_message_id from the existing lineage record.
    existing_lineage = await MessageLineage.find_one(
        MessageLineage.cloned_message_id == body.message_id,
    )
    if existing_lineage is not None:
        original_message_id = existing_lineage.original_message_id
        original_sender_user_id = existing_lineage.original_sender_user_id
    else:
        original_message_id = body.message_id
        original_sender_user_id = original_message.send_user_id

    # Check if the user has already forwarded this message
    already_forwarded = await _has_user_forwarded_message(
        current_user, original_message_id
    )
    if already_forwarded:
        raise HTTPException(
            status_code=400,
            detail="You have already forwarded this message.",
        )

    # Find users who have blocked the forwarder
    blocked_entries = await Blocked.find(
        Blocked.blocked_user_id == current_user
    ).to_list()
    blocked_by_user_ids = {b.blocked_by_user_id for b in blocked_entries}

    # Pick a random recipient (excluding the forwarder and anyone
    # who has blocked the forwarder)
    all_users = await User.find(
        User.user_id != current_user,
    ).to_list()

    eligible = [u for u in all_users if u.user_id not in blocked_by_user_ids]

    if not eligible:
        raise HTTPException(
            status_code=400,
            detail=(
                "No other users available to receive "
                "the forwarded message."
            ),
        )

    recipient = random.choice(eligible)

    # Create the forwarded message using the shared utility
    cloned_message = await _send_message_to_user(
        sender_user_id=current_user,
        message_content=original_message.message,
        recipient_user_id=recipient.user_id,
    )

    # Record the lineage
    lineage = MessageLineage(
        original_message_id=original_message_id,
        cloned_message_id=cloned_message.message_id,
        original_sender_user_id=original_sender_user_id,
    )
    await lineage.insert()

    return SuccessResponse(
        detail="Message forwarded."
    )


@router.get(
    "/unread_messages",
    response_model=UnreadMessagesResponse,
    summary="Get unread message count for the authenticated user",
    description=(
        "Returns the number of messages received by the authenticated user "
        "that have not yet been seen (seen_timestamp is null). No request "
        "body is required."
    ),
)
async def unread_messages(
    current_user: str = Depends(get_current_user),
):
    """Return the count of unread messages for the authenticated user."""
    count = await Message.find(
        Message.receive_user_id == current_user,
        Message.seen_timestamp == None,  # noqa: E711
    ).count()

    return UnreadMessagesResponse(unread_count=count)


@router.get(
    "/karma_count",
    response_model=KarmaCountResponse,
    summary="Get karma score for the authenticated user",
    description=(
        "Calculates the karma score for the authenticated user based on "
        "messages they have sent, including karma from forwarded copies. "
        "Karma = (number of 'up' reactions) minus (number of 'down' "
        "reactions). No request body is required."
    ),
)
async def karma_count(
    current_user: str = Depends(get_current_user),
):
    """Return the karma score for the authenticated user."""
    # Count messages sent by the user with 'up' reaction
    up_count = await Message.find(
        Message.send_user_id == current_user,
        Message.reaction_type == "up",
    ).count()

    # Count messages sent by the user with 'down' reaction
    down_count = await Message.find(
        Message.send_user_id == current_user,
        Message.reaction_type == "down",
    ).count()

    karma = up_count - down_count

    # Add karma from forwarded messages where the user is the original sender
    lineage_records = await MessageLineage.find(
        MessageLineage.original_sender_user_id == current_user,
    ).to_list()

    for record in lineage_records:
        cloned_msg = await Message.find_one(
            Message.message_id == record.cloned_message_id
        )
        if cloned_msg and cloned_msg.reaction_type == "up":
            karma += 1
        elif cloned_msg and cloned_msg.reaction_type == "down":
            karma -= 1

    return KarmaCountResponse(karma=karma)


@router.get(
    "/message_history",
    response_model=MessageHistoryResponse,
    summary="Get message history for the authenticated user",
    description=(
        "Returns paginated messages where the authenticated user is the "
        "sender or receiver. The other party's user ID is deterministically "
        "anonymized using SHA-256. Results are ordered by sent_timestamp "
        "descending (latest first). Use the page and page_size query "
        "parameters to control pagination."
    ),
)
async def message_history(
    current_user: str = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Number of messages per page"
    ),
):
    """Return paginated messages where the user is sender or receiver."""
    # Count total matching messages
    total_items = await Message.find(
        {"$or": [
            {"send_user_id": current_user},
            {"receive_user_id": current_user},
        ]}
    ).count()

    total_pages = max(1, math.ceil(total_items / page_size))
    skip = (page - 1) * page_size

    # Fetch the requested page, sorted newest-first
    messages = (
        await Message.find(
            {"$or": [
                {"send_user_id": current_user},
                {"receive_user_id": current_user},
            ]}
        )
        .sort(-Message.sent_timestamp)
        .skip(skip)
        .limit(page_size)
        .to_list()
    )

    # Mark messages as seen where the requesting user is the receiver
    now = datetime.now(timezone.utc)
    for msg in messages:
        if msg.receive_user_id == current_user and msg.seen_timestamp is None:
            msg.seen_timestamp = now
            await msg.save()

    out: list[MessageOut] = []
    for msg in messages:
        # Anonymize the "other" user
        if msg.send_user_id == current_user:
            other_id = anonymize_user_id(msg.receive_user_id)
        else:
            other_id = anonymize_user_id(msg.send_user_id)

        # Get forward stats for messages the user sent
        forward_count = 0
        total_karma = 0
        if msg.send_user_id == current_user:
            forward_count, total_karma = await _get_forward_stats(
                msg.message_id, current_user
            )

        out.append(
            MessageOut(
                message_id=msg.message_id,
                send_user_id=(
                    current_user
                    if msg.send_user_id == current_user
                    else other_id
                ),
                receive_user_id=(
                    current_user
                    if msg.receive_user_id == current_user
                    else other_id
                ),
                message=msg.message,
                sent_timestamp=msg.sent_timestamp,
                seen_timestamp=msg.seen_timestamp,
                reaction_type=msg.reaction_type,
                reported=msg.reported,
                forward_count=forward_count,
                total_karma=total_karma,
            )
        )

    return MessageHistoryResponse(
        messages=out,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.post(
    "/block_user",
    response_model=SuccessResponse,
    summary="Block a user",
    description=(
        "Blocks the sender of the specified message. The blocker is "
        "determined from the auth token. If the block record already "
        "exists, this is a no-op."
    ),
)
async def block_user(
    body: BlockUserRequest,
    current_user: str = Depends(get_current_user),
):
    """Block the sender of a message. If already blocked, this is a no-op."""
    # Look up the message to find the sender
    message = await Message.find_one(Message.message_id == body.message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    # Only the receiver of the message can block the sender
    if message.receive_user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="You can only block users who have sent you a message.",
        )

    blocked_user_id = message.send_user_id

    existing = await Blocked.find_one(
        Blocked.blocked_by_user_id == current_user,
        Blocked.blocked_user_id == blocked_user_id,
    )
    if existing is None:
        entry = Blocked(
            blocked_user_id=blocked_user_id,
            blocked_by_user_id=current_user,
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
        "Removes the block record for the specified user. The "
        "blocked_user_id can be either the anonymized ID (anon_...) "
        "returned by /block_list or the raw Firebase UID. The "
        "unblocker is determined from the auth token. If no such "
        "block exists, this is a no-op."
    ),
)
async def unblock_user(
    body: UnblockUserRequest,
    current_user: str = Depends(get_current_user),
):
    """Unblock a user. Accepts anonymized or raw user ID."""
    # If the ID starts with "anon_", resolve it by iterating the
    # user's blocked entries and matching the anonymized form.
    if body.blocked_user_id.startswith("anon_"):
        entries = await Blocked.find(
            Blocked.blocked_by_user_id == current_user
        ).to_list()
        matched = None
        for entry in entries:
            anon = anonymize_user_id(entry.blocked_user_id)
            if anon == body.blocked_user_id:
                matched = entry
                break
        if matched is not None:
            await matched.delete()
            return SuccessResponse(detail="User unblocked.")
        return SuccessResponse(detail="User was not blocked.")

    # Otherwise treat it as a raw Firebase UID
    existing = await Blocked.find_one(
        Blocked.blocked_by_user_id == current_user,
        Blocked.blocked_user_id == body.blocked_user_id,
    )
    if existing is not None:
        await existing.delete()
        return SuccessResponse(detail="User unblocked.")
    return SuccessResponse(detail="User was not blocked.")


@router.post(
    "/block_list",
    response_model=BlockListResponse,
    summary="Get block list for the authenticated user",
    description=(
        "Returns a paginated list of all user IDs that the authenticated "
        "user has blocked, along with the messages each blocked user sent "
        "to them. The returned user IDs are deterministically anonymized "
        "using SHA-256. Results are ordered by blocked_timestamp descending "
        "(latest first). Use the page and page_size query parameters to "
        "control pagination."
    ),
)
async def block_list(
    current_user: str = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        20, ge=1, le=100, description="Number of blocked users per page"
    ),
):
    """Return paginated blocked users with their messages to the blocker."""
    # Count total blocked users
    total_items = await Blocked.find(
        Blocked.blocked_by_user_id == current_user
    ).count()

    total_pages = max(1, math.ceil(total_items / page_size))
    skip = (page - 1) * page_size

    # Fetch the requested page, sorted newest-first by blocked_timestamp
    entries = (
        await Blocked.find(Blocked.blocked_by_user_id == current_user)
        .sort(-Blocked.blocked_timestamp)
        .skip(skip)
        .limit(page_size)
        .to_list()
    )

    blocked_users: list[BlockedUserEntry] = []
    for entry in entries:
        anonymized_id = anonymize_user_id(entry.blocked_user_id)

        # Find messages sent by the blocked user to the blocker
        messages = (
            await Message.find(
                Message.send_user_id == entry.blocked_user_id,
                Message.receive_user_id == current_user,
            )
            .sort(-Message.sent_timestamp)
            .to_list()
        )

        message_outs = [
            MessageOut(
                message_id=msg.message_id,
                send_user_id=anonymized_id,
                receive_user_id=current_user,
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

    return BlockListResponse(
        blocked_users=blocked_users,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.post(
    "/react_to_message",
    response_model=SuccessResponse,
    summary="React to a message",
    description=(
        "Sets the reaction on a message. Accepted reaction values are "
        "'up', 'down', or null (to clear the reaction)."
    ),
)
async def react_to_message(
    body: ReactToMessageRequest,
    current_user: str = Depends(get_current_user),
):
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

    # Only the receiver of the message can react to it
    if message.receive_user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="You can only react to messages you received.",
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
async def report_message(
    body: ReportMessageRequest,
    current_user: str = Depends(get_current_user),
):
    """Mark a message as reported."""
    message = await Message.find_one(Message.message_id == body.message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail=f"Message with message_id '{body.message_id}' not found.",
        )

    # Only the receiver of the message can report it
    if message.receive_user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="You can only report messages you received.",
        )

    message.reported = True
    await message.save()

    return SuccessResponse(
        detail=f"Message {body.message_id} reported."
    )


@router.post(
    "/delete_account",
    response_model=SuccessResponse,
    summary="Delete the authenticated user's account",
    description=(
        "Deletes the authenticated user and all related data (messages, "
        "block records). The user will no longer appear as an eligible "
        "recipient for new messages."
    ),
)
async def delete_account(
    current_user: str = Depends(get_current_user),
):
    """Delete the authenticated user's account and all related data."""
    user = await User.find_one(User.user_id == current_user)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    # Delete all messages where the user is sender or receiver
    msg_result = await Message.find(
        {"$or": [
            {"send_user_id": current_user},
            {"receive_user_id": current_user},
        ]}
    ).delete()

    # Delete all block records where the user is the blocker or blocked
    block_result = await Blocked.find(
        {"$or": [
            {"blocked_by_user_id": current_user},
            {"blocked_user_id": current_user},
        ]}
    ).delete()

    # Delete the user document
    await user.delete()

    return SuccessResponse(
        detail=(
            f"Account deleted. Removed {msg_result.deleted_count} message(s) "
            f"and {block_result.deleted_count} block record(s)."
        )
    )
