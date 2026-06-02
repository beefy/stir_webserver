"""
Initial migration: Creates the messages and blocked collections.

This migration sets up the initial database schema by defining the
Message and Blocked document models with Beanie ODM.
"""

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from models.message import Message
from models.blocked import Blocked


async def upgrade(connection_string: str, database_name: str) -> None:
    """
    Run the migration to initialize Beanie with the Message and Blocked models.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    await init_beanie(
        database=database,
        document_models=[Message, Blocked],
    )

    print("Migration 001_initial complete: messages and blocked collections created.")


async def downgrade(connection_string: str, database_name: str) -> None:
    """
    Roll back the migration by dropping the messages and blocked collections.

    Args:
        connection_string: MongoDB connection string.
        database_name: Name of the database to use.
    """
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    collections = await database.list_collection_names()
    for collection_name in ["messages", "blocked"]:
        if collection_name in collections:
            await database[collection_name].drop()
            print(f"Dropped collection: {collection_name}")

    print("Migration 001_initial rolled back: messages and blocked collections dropped.")
