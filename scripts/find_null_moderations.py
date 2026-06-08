"""
Script to find all moderation records with a null moderation_action.

Usage:
    PYTHONPATH=. python scripts/find_null_moderations.py

Environment variables:
    MONGODB_CONNECTION_STRING: MongoDB connection string
        (default: mongodb://localhost:27017)
    MONGODB_DATABASE_NAME: Database name
        (default: stir_webserver)
"""

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def main() -> None:
    """Query the moderations collection for records with null action."""
    connection_string = os.getenv(
        "MONGODB_CONNECTION_STRING",
        "mongodb://localhost:27017",
    )
    database_name = os.getenv(
        "MONGODB_DATABASE_NAME",
        "stir_webserver",
    )

    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]
    collection = database["moderations"]

    cursor = collection.find(
        {"moderation_action": None},
    ).sort("moderation_datetime", -1)

    count = 0
    async for doc in cursor:
        count += 1
        print(
            f"moderation_id: {doc.get('moderation_id')}, "
            f"message_id: {doc.get('message_id')}, "
            f"moderation_datetime: {doc.get('moderation_datetime')}"
        )

    print(f"\nTotal null-action moderation records: {count}")


if __name__ == "__main__":
    asyncio.run(main())
