"""Request and response models for the stir_webserver API."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Request body for POST /login."""

    user_id: str = Field(
        ...,
        description="Firebase user ID to register",
        json_schema_extra={"example": "firebase-uid-123"},
    )


class SendMessageRequest(BaseModel):
    """Request body for POST /send_message."""

    send_user_id: str = Field(
        ...,
        description="Firebase user ID of the sender",
        json_schema_extra={"example": "firebase-uid-123"},
    )
    message_content: str = Field(
        ...,
        description="Text content of the message (max 255 characters)",
        max_length=255,
        json_schema_extra={"example": "Hello there!"},
    )


class BlockUserRequest(BaseModel):
    """Request body for POST /block_user."""

    blocked_by_user_id: str = Field(
        ...,
        description="Firebase user ID of the user doing the blocking",
        json_schema_extra={"example": "firebase-uid-123"},
    )
    blocked_user_id: str = Field(
        ...,
        description="Firebase user ID of the user being blocked",
        json_schema_extra={"example": "firebase-uid-456"},
    )


class UnblockUserRequest(BaseModel):
    """Request body for POST /unblock_user."""

    blocked_by_user_id: str = Field(
        ...,
        description="Firebase user ID of the user who originally blocked",
        json_schema_extra={"example": "firebase-uid-123"},
    )
    blocked_user_id: str = Field(
        ...,
        description="Firebase user ID of the user being unblocked",
        json_schema_extra={"example": "firebase-uid-456"},
    )


class BlockListRequest(BaseModel):
    """Request body for POST /block_list."""

    blocked_by_user_id: str = Field(
        ...,
        description="Firebase user ID to fetch the block list for",
        json_schema_extra={"example": "firebase-uid-123"},
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class BlockListResponse(BaseModel):
    """Response for POST /block_list."""

    blocked_user_ids: list[str] = Field(
        description="List of anonymized blocked user IDs"
    )


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    detail: str


class MessageOut(BaseModel):
    """A single message returned in message history."""

    message_id: str = Field(description="MongoDB document ID")
    send_user_id: str = Field(
        description="Sender ID (anonymized if not the requesting user)"
    )
    receive_user_id: str = Field(
        description="Receiver ID (anonymized if not the requesting user)"
    )
    message: str = Field(description="Text content of the message")
    sent_timestamp: datetime = Field(description="When the message was sent")
    seen_timestamp: datetime | None = Field(
        description="When the message was seen, if at all"
    )
    reaction_type: str | None = Field(
        description="Reaction type, e.g. 'like' or 'heart'"
    )
    reported: bool = Field(
        description="Whether the message has been reported"
    )


class MessageHistoryResponse(BaseModel):
    """Response for GET /message_history."""

    messages: list[MessageOut]
