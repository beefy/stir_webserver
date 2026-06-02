from beanie import Document
from datetime import datetime
from typing import Optional


class Message(Document):
    """Represents a message between two users."""

    send_user_id: str
    receive_user_id: str
    seen_timestamp: Optional[datetime] = None  # When the message was seen
    reaction_type: Optional[str] = None  # Reaction type (e.g., "like", "heart", etc.)
    reported: bool = False  # Whether the message has been reported

    class Settings:
        name = "messages"
        use_state_management = True
