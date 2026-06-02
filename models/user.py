from beanie import Document


class User(Document):
    """Represents a registered user."""

    user_id: str

    class Settings:
        name = "users"
        use_state_management = True
