"""
Migration 002: Adds a UUID ``message_id`` field to all messages.

Adds the ``message_id`` field to all existing messages, assigning each a
UUID v4 string.
"""

import uuid

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Add the ``message_id`` field to all documents in the messages collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]
    collection = database["messages"]

    cursor = collection.find({"message_id": {"$exists": False}})
    updated = 0

    async for doc in cursor:
        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"message_id": str(uuid.uuid4())}},
        )
        updated += 1

    print(
        f"Migration 002_message_id complete. "
        f"Assigned UUID message_id to {updated} document(s)."
    )


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Remove the ``message_id`` field from all documents in the messages
    collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]
    collection = database["messages"]

    result = await collection.update_many(
        {},
        {"$unset": {"message_id": ""}},
    )

    print(
        f"Migration 002_message_id rolled back. "
        f"Removed message_id from {result.modified_count} document(s)."
    )
