"""
Migration 004: Creates the audits collection.

Creates the ``audits`` collection for logging user data access/deletion
requests.
"""

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Create the audits collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    existing = await database.list_collection_names()
    if "audits" not in existing:
        await database.create_collection("audits")
        print("Created collection: audits")
    else:
        print("Collection already exists: audits")

    print("Migration 004_audit complete.")


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Drop the audits collection.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    collections = await database.list_collection_names()
    if "audits" in collections:
        await database["audits"].drop()
        print("Dropped collection: audits")

    print("Migration 004_audit rolled back.")
