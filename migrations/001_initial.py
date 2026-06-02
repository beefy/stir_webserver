"""
Initial migration: Creates the messages, blocked, and users collections.

This migration sets up the initial database schema by creating the
collections and any necessary indexes directly via the Motor driver.
"""

from motor.motor_asyncio import AsyncIOMotorClient


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Run the migration to create the collections.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    existing = await database.list_collection_names()

    # Create messages collection
    if "messages" not in existing:
        await database.create_collection("messages")
        print("Created collection: messages")
    else:
        print("Collection already exists: messages")

    # Create blocked collection
    if "blocked" not in existing:
        await database.create_collection("blocked")
        print("Created collection: blocked")
    else:
        print("Collection already exists: blocked")

    # Create users collection
    if "users" not in existing:
        await database.create_collection("users")
        print("Created collection: users")
    else:
        print("Collection already exists: users")

    print("Migration 001_initial complete.")


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Roll back the migration by dropping the collections.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    collections = await database.list_collection_names()
    for collection_name in ["messages", "blocked", "users"]:
        if collection_name in collections:
            await database[collection_name].drop()
            print(f"Dropped collection: {collection_name}")

    print("Migration 001_initial rolled back.")
