from beanie import Document
from datetime import datetime


class Blocked(Document):
    """Represents a user blocking another user."""

    blocked_user_id: str
    blocked_by_user_id: str
    blocked_timestamp: datetime  # When the block occurred

    class Settings:
        name = "blocked"
        use_state_management = True
