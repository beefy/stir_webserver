"""Request and response models for the stir_webserver API."""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    """Request body for POST /send_message."""

    message_content: str = Field(
        ...,
        description="Text content of the message (max 255 characters)",
        max_length=255,
        json_schema_extra={"example": "Hello there!"},
    )


class BlockUserRequest(BaseModel):
    """Request body for POST /block_user."""

    message_id: str = Field(
        ...,
        description=(
            "UUID of a message sent by the user to block. "
            "The sender of this message will be blocked."
        ),
        json_schema_extra={
            "example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        },
    )


class UnblockUserRequest(BaseModel):
    """Request body for POST /unblock_user."""

    blocked_user_id: str = Field(
        ...,
        description="Firebase user ID of the user being unblocked",
        json_schema_extra={"example": "firebase-uid-456"},
    )


class ReactToMessageRequest(BaseModel):
    """Request body for POST /react_to_message."""

    message_id: str = Field(
        ...,
        description="UUID identifying the message to react to",
        json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    )
    reaction_content: str | None = Field(
        ...,
        description="Reaction content: 'up', 'down', or null to clear",
        json_schema_extra={"example": "up"},
    )


class ReportMessageRequest(BaseModel):
    """Request body for POST /report_message."""

    message_id: str = Field(
        ...,
        description="UUID identifying the message to report",
        json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    detail: str


class MessageOut(BaseModel):
    """A single message returned in message history."""

    message_id: str = Field(description="UUID identifying the message")
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


class PaginationInfo(BaseModel):
    """Pagination metadata included in paginated responses."""

    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Number of items per page")
    total_items: int = Field(
        description="Total number of items across all pages"
    )
    total_pages: int = Field(description="Total number of pages")


class MessageHistoryResponse(BaseModel):
    """Response for GET /message_history."""

    messages: list[MessageOut]
    pagination: PaginationInfo


class UnreadMessagesResponse(BaseModel):
    """Response for GET /unread_messages."""

    unread_count: int = Field(
        description="Number of unread messages for the authenticated user"
    )


class BlockedUserEntry(BaseModel):
    """A blocked user and the messages they sent to the blocker."""

    blocked_user_id: str = Field(
        description="Anonymized user ID of the blocked user"
    )
    messages: list[MessageOut] = Field(
        description="Messages sent by the blocked user to the blocker"
    )


class BlockListResponse(BaseModel):
    """Response for POST /block_list."""

    blocked_users: list[BlockedUserEntry] = Field(
        description="List of blocked users with their messages"
    )
    pagination: PaginationInfo
