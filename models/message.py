from beanie import Document
from datetime import datetime
from typing import Optional


class Message(Document):
    """Represents a message between two users."""

    message_id: str  # UUID identifying the message
    send_user_id: str
    receive_user_id: Optional[str] = None
    message: str
    sent_timestamp: datetime
    seen_timestamp: Optional[datetime] = None
    reaction_type: Optional[str] = None
    reported: bool = False

    class Settings:
        name = "messages"
        use_state_management = True
