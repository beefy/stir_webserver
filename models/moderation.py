from beanie import Document
from datetime import datetime
from typing import Optional


class Moderation(Document):
    """Represents a moderation action on a reported message."""

    moderation_id: str  # UUID identifying the moderation record
    message_id: str  # UUID of the reported message
    moderation_action: Optional[str] = None  # "ban" or "dismiss" or None
    moderation_datetime: datetime  # When the moderation action occurred

    class Settings:
        name = "moderations"
        use_state_management = True
