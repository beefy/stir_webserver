"""
Migration 003: Adds the ``is_deleted`` field to all user documents.

Sets ``is_deleted`` to ``False`` for all existing users.
"""

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Add the ``is_deleted`` field to all documents in the users collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]
    collection = database["users"]

    result = await collection.update_many(
        {"is_deleted": {"$exists": False}},
        {"$set": {"is_deleted": False}},
    )

    print(
        f"Migration 003_is_deleted complete. "
        f"Set is_deleted=False on {result.modified_count} document(s)."
    )


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Remove the ``is_deleted`` field from all documents in the users
    collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]
    collection = database["users"]

    result = await collection.update_many(
        {},
        {"$unset": {"is_deleted": ""}},
    )

    print(
        f"Migration 003_is_deleted rolled back. "
        f"Removed is_deleted from {result.modified_count} document(s)."
    )
