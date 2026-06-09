from beanie import Document
from datetime import datetime
from typing import Optional


class Audit(Document):
    """Represents an audit log entry for user data access/deletion."""

    audit_id: str  # UUID identifying the audit record
    request_type: str  # "view", "export", or "delete"
    user_id: str  # Firebase UID of the requesting user
    user_email_anon: Optional[str] = None  # Deterministically anonymized email
    id_verification_method: str  # How the user's identity was verified
    request_datetime: datetime  # When the request was initiated
    finish_datetime: Optional[datetime] = None  # When the request completed
    outcome: str  # "success" or "failure"

    class Settings:
        name = "audits"
        use_state_management = True
