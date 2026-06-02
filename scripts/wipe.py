"""
Wipe script: Deletes all data from all collections.

Usage:
    python scripts/wipe.py

Requires PYTHONPATH to include the project root, e.g.:
    PYTHONPATH=. python scripts/wipe.py

Environment variables:
    MONGODB_CONNECTION_STRING: MongoDB connection string
        (default: mongodb://localhost:27017)
    MONGODB_DATABASE_NAME: Database name
        (default: stir_webserver)
"""

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def wipe() -> None:
    """Delete all documents from the blocked, messages, and users collections."""
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

    collections = ["blocked", "messages", "users"]
    total = 0

    for name in collections:
        result = await database[name].delete_many({})
        count = result.deleted_count
        total += count
        print(f"Deleted {count} document(s) from '{name}'.")

    print(f"Wipe complete. Removed {total} document(s) total.")


if __name__ == "__main__":
    asyncio.run(wipe())
