"""
FastAPI web server for stir_webserver.

Endpoints:
    POST /login          — Register a user
    POST /send_message   — Send a message to a random user
    GET  /message_history — Get message history for a user
"""

import os
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from beanie import init_beanie
from fastapi import FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from app.utils import anonymize_user_id
from models.message import Message
from models.user import User
from models.blocked import Blocked


# ---------------------------------------------------------------------------
# Lifespan — connect to MongoDB on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    connection_string = os.getenv(
        "MONGODB_CONNECTION_STRING",
        "mongodb://localhost:27017",
    )
    database_name = os.getenv(
        "MONGODB_DATABASE_NAME",
        "stir_webserver",
    )
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    await init_beanie(
        database=database,
        document_models=[Message, User, Blocked],
    )
    yield


app = FastAPI(title="stir_webserver", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    user_id: str = Field(..., description="Firebase user ID to register")


class SendMessageRequest(BaseModel):
    send_user_id: str = Field(
        ..., description="Firebase user ID of the sender"
    )
    message_content: str = Field(
        ..., description="Text content of the message"
    )


class SuccessResponse(BaseModel):
    success: bool = True
    detail: str


class MessageOut(BaseModel):
    message_id: str
    send_user_id: str
    receive_user_id: str
    message: str
    sent_timestamp: datetime
    seen_timestamp: datetime | None
    reaction_type: str | None
    reported: bool


class MessageHistoryResponse(BaseModel):
    messages: list[MessageOut]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/login", response_model=SuccessResponse)
async def login(body: LoginRequest):
    """Register a user. If the user already exists, this is a no-op."""
    existing = await User.find_one(User.user_id == body.user_id)
    if existing is None:
        user = User(user_id=body.user_id)
        await user.insert()
        return SuccessResponse(detail=f"User '{body.user_id}' registered.")
    return SuccessResponse(detail=f"User '{body.user_id}' already exists.")


@app.post("/send_message", response_model=SuccessResponse)
async def send_message(body: SendMessageRequest):
    """Send a message to a random user.

    Validates that the message is <= 255 characters, picks a random
    recipient from the users table (excluding the sender), and inserts
    the message.
    """
    if len(body.message_content) > 255:
        raise HTTPException(
            status_code=400,
            detail="Message must be 255 characters or fewer.",
        )

    # Pick a random recipient (excluding the sender)
    all_users = await User.find(
        User.user_id != body.send_user_id
    ).to_list()

    if not all_users:
        raise HTTPException(
            status_code=400,
            detail="No other users available to receive the message.",
        )

    recipient = random.choice(all_users)

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
        detail=(
            f"Message sent to user '{recipient.user_id}'."
        )
    )


@app.get("/message_history", response_model=MessageHistoryResponse)
async def message_history(
    user_id: str = Query(..., description="User ID to fetch history for"),
):
    """Return all messages where the user is sender or receiver.

    The "other" party's user ID is deterministically anonymized.
    Results are ordered by sent_timestamp ascending.
    """
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
