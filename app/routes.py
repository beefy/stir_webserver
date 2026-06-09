"""API route handlers for stir_webserver."""

import asyncio
import math
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from app.auth import AuthError, get_firebase_user
from app.types import (
    BlockedUserEntry,
    BlockListResponse,
    BlockUserRequest,
    FirebaseUserInfo,
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
    ViewAccountResponse,
)
from app.utils import (
    anonymize_email,
    anonymize_user_id,
    get_current_user,
    get_current_user_unverified,
    run_moderation,
)
from models.audit import Audit
from models.blocked import Blocked
from models.message import Message
from models.moderation import Moderation
from models.user import User

router = APIRouter()


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
    current_user: str = Depends(get_current_user_unverified),
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

    # Check if the sender is shadow-banned
    sender = await User.find_one(User.user_id == current_user)
    if sender is not None and sender.shadow_banned:
        # Shadow-banned users' messages have no real recipient
        message = Message(
            message_id=str(uuid.uuid4()),
            send_user_id=current_user,
            receive_user_id=None,
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

    message = Message(
        message_id=str(uuid.uuid4()),
        send_user_id=current_user,
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
        "messages they have sent. Karma = (number of 'up' reactions) "
        "minus (number of 'down' reactions). No request body is required."
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

    return KarmaCountResponse(karma=up_count - down_count)


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
    """Mark a message as reported and trigger async moderation."""
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

    # Fire-and-forget moderation via DeepSeek (does not block the response)
    asyncio.ensure_future(
        run_moderation(body.message_id, message.message)
    )

    return SuccessResponse(
        detail=f"Message {body.message_id} reported."
    )


@router.get(
    "/view_account",
    response_model=ViewAccountResponse,
    summary="View account details",
    description=(
        "Returns all data about the authenticated user's account, "
        "including the Firebase user record and all associated data "
        "from MongoDB (user document, messages, and block records). "
        "Requires a request_type query parameter: 'view' or 'export'. "
        "All requests are logged to the audit table."
    ),
)
async def view_account(
    authorization: str | None = Header(None),
    current_user: str = Depends(get_current_user),
    request_type: str = Query(
        ...,
        description="Type of request: 'view' or 'export'",
    ),
):
    """Return Firebase and all MongoDB data for the authenticated user."""
    # Validate request_type
    if request_type not in ("view", "export"):
        raise HTTPException(
            status_code=400,
            detail="request_type must be 'view' or 'export'.",
        )

    request_datetime = datetime.now(timezone.utc)

    # Fetch the full Firebase user record
    try:
        firebase_data = await get_firebase_user(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        )

    # Create the audit log entry
    user_email = firebase_data.get("email")
    email_anon = anonymize_email(user_email)
    audit = Audit(
        audit_id=str(uuid.uuid4()),
        request_type=request_type,
        user_id=current_user,
        user_email_anon=email_anon,
        id_verification_method="firebase_token",
        request_datetime=request_datetime,
        finish_datetime=datetime.now(timezone.utc),
        outcome="success",
    )
    await audit.insert()

    def _serialize(obj: dict) -> dict:
        """Convert PydanticObjectId to string and anonymize non-self
        user IDs for JSON serialization."""
        result = {}
        for k, v in obj.items():
            # Convert ObjectId to string
            if hasattr(v, "__class__") and "ObjectId" in type(v).__name__:
                result[k] = str(v)
            # Anonymize user ID fields that don't belong to the
            # authenticated user
            elif k in ("send_user_id", "receive_user_id",
                       "blocked_user_id", "blocked_by_user_id"):
                result[k] = (
                    v if v == current_user else anonymize_user_id(v)
                )
            else:
                result[k] = v
        return result

    # Fetch the MongoDB user document
    user_doc = await User.find_one(User.user_id == current_user)
    user_data = _serialize(user_doc.model_dump()) if user_doc else None

    # Fetch all messages where the user is sender or receiver
    messages = await Message.find(
        {"$or": [
            {"send_user_id": current_user},
            {"receive_user_id": current_user},
        ]}
    ).sort(-Message.sent_timestamp).to_list()
    messages_data = [_serialize(m.model_dump()) for m in messages]

    # Fetch block records where the user is the blocker
    blocked_by_me = await Blocked.find(
        Blocked.blocked_by_user_id == current_user
    ).sort(-Blocked.blocked_timestamp).to_list()
    blocked_by_me_data = [_serialize(b.model_dump()) for b in blocked_by_me]

    # Fetch block records where the user is the blocked user
    blocked_me = await Blocked.find(
        Blocked.blocked_user_id == current_user
    ).sort(-Blocked.blocked_timestamp).to_list()
    blocked_me_data = [_serialize(b.model_dump()) for b in blocked_me]

    # Fetch moderation records for messages involving the user
    user_messages = await Message.find(
        {"$or": [
            {"send_user_id": current_user},
            {"receive_user_id": current_user},
        ]}
    ).to_list()
    user_message_ids = [m.message_id for m in user_messages]
    moderations = await Moderation.find(
        {"message_id": {"$in": user_message_ids}}
    ).sort(-Moderation.moderation_datetime).to_list()
    moderations_data = [_serialize(m.model_dump()) for m in moderations]

    # Fetch audit records for the user (after inserting the new one).
    # Also fetch audit records with the same anonymized email to catch
    # data from previous accounts that used the same email address.
    audits = await Audit.find(
        {"$or": [
            {"user_id": current_user},
            {"user_email_anon": email_anon},
        ]}
    ).sort(-Audit.request_datetime).to_list()
    audits_data = [_serialize(a.model_dump()) for a in audits]

    return ViewAccountResponse(
        firebase=FirebaseUserInfo(**firebase_data),
        user=user_data,
        messages=messages_data,
        blocked_by_me=blocked_by_me_data,
        blocked_me=blocked_me_data,
        moderations=moderations_data,
        audits=audits_data,
    )


@router.post(
    "/delete_account",
    response_model=SuccessResponse,
    summary="Delete the authenticated user's account",
    description=(
        "Deletes the authenticated user and all related data (messages, "
        "block records). The user will no longer appear as an eligible "
        "recipient for new messages. The deletion is logged to the audit "
        "table."
    ),
)
async def delete_account(
    authorization: str | None = Header(None),
    current_user: str = Depends(get_current_user),
):
    """Delete the authenticated user's account and all related data."""
    request_datetime = datetime.now(timezone.utc)

    # Fetch the full Firebase user record for audit logging
    try:
        firebase_data = await get_firebase_user(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        )

    user = await User.find_one(User.user_id == current_user)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    # Find messages involving the user to get their message IDs
    user_messages = await Message.find(
        {"$or": [
            {"send_user_id": current_user},
            {"receive_user_id": current_user},
        ]}
    ).to_list()
    user_message_ids = [m.message_id for m in user_messages]

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

    # Delete moderation records for messages involving the user
    mod_result = await Moderation.find(
        {"message_id": {"$in": user_message_ids}}
    ).delete()

    # Delete the user document
    await user.delete()

    # Log the audit entry
    user_email = firebase_data.get("email")
    email_anon = anonymize_email(user_email)
    audit = Audit(
        audit_id=str(uuid.uuid4()),
        request_type="delete",
        user_id=current_user,
        user_email_anon=email_anon,
        id_verification_method="firebase_token",
        request_datetime=request_datetime,
        finish_datetime=datetime.now(timezone.utc),
        outcome="success",
    )
    await audit.insert()

    return SuccessResponse(
        detail=(
            f"Account deleted. Removed {msg_result.deleted_count} message(s), "
            f"{block_result.deleted_count} block record(s), "
            f"and {mod_result.deleted_count} moderation record(s)."
        )
    )
