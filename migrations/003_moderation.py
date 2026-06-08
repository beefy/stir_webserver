"""
Migration 003: Adds the moderations collection and shadow_banned field.

Creates the ``moderations`` collection and adds the ``shadow_banned``
field (default false) to all existing user documents.
"""

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Create the moderations collection and add shadow_banned to users.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    # Create moderations collection
    existing = await database.list_collection_names()
    if "moderations" not in existing:
        await database.create_collection("moderations")
        print("Created collection: moderations")
    else:
        print("Collection already exists: moderations")

    # Add shadow_banned field to all users (default false)
    result = await database["users"].update_many(
        {"shadow_banned": {"$exists": False}},
        {"$set": {"shadow_banned": False}},
    )
    print(
        f"Added shadow_banned field to {result.modified_count} user "
        "document(s)."
    )

    print("Migration 003_moderation complete.")


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Drop the moderations collection and remove shadow_banned from users.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    # Drop moderations collection
    collections = await database.list_collection_names()
    if "moderations" in collections:
        await database["moderations"].drop()
        print("Dropped collection: moderations")

    # Remove shadow_banned field from users
    result = await database["users"].update_many(
        {},
        {"$unset": {"shadow_banned": ""}},
    )
    print(
        f"Removed shadow_banned from {result.modified_count} user document(s)."
    )

    print("Migration 003_moderation rolled back.")
