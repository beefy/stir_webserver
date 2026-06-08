from beanie import Document


class User(Document):
    """Represents a registered user."""

    user_id: str
    shadow_banned: bool = False

    class Settings:
        name = "users"
        use_state_management = True
