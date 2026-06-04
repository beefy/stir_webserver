"""
Migration 003: Creates the message_lineage collection.

Creates the ``message_lineage`` collection used to track forwarded messages
and their original sources.
"""

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Create the ``message_lineage`` collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    existing = await database.list_collection_names()

    if "message_lineage" not in existing:
        await database.create_collection("message_lineage")
        print("Created collection: message_lineage")
    else:
        print("Collection already exists: message_lineage")

    print("Migration 003_message_lineage complete.")


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Drop the ``message_lineage`` collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    collections = await database.list_collection_names()
    if "message_lineage" in collections:
        await database["message_lineage"].drop()
        print("Dropped collection: message_lineage")

    print("Migration 003_message_lineage rolled back.")
