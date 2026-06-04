from beanie import Document


class MessageLineage(Document):
    """Tracks forwarded messages and their original source.

    When a message is forwarded, a new message is created (cloned_message_id)
    and linked back to the original message (original_message_id). If the
    message being forwarded was itself a forward, the original_message_id
    points to the very first message in the chain.
    """

    original_message_id: str  # The very first message in the forward chain
    cloned_message_id: str    # The newly created forwarded message
    original_sender_user_id: str  # The sender of the original message

    class Settings:
        name = "message_lineage"
        use_state_management = True
