"""
Migration runner for Beanie ODM migrations.

Usage:
    python migrations/migrate.py [up|down]

Environment variables:
    MONGODB_CONNECTION_STRING: MongoDB connection string (default: mongodb://localhost:27017)
    MONGODB_DATABASE_NAME: Database name (default: stir_webserver)
"""

import asyncio
import os
import sys
from importlib import import_module

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


MIGRATIONS = [
    "001_initial",
]


async def run_migrations(direction: str) -> None:
    """Run all migrations in the specified direction."""
    connection_string = os.getenv(
        "MONGODB_CONNECTION_STRING",
        "mongodb://localhost:27017",
    )
    database_name = os.getenv(
        "MONGODB_DATABASE_NAME",
        "stir_webserver",
    )

    if direction == "up":
        for migration_name in MIGRATIONS:
            module = import_module(f"migrations.{migration_name}")
            print(f"Running migration: {migration_name} (up)")
            await module.upgrade(connection_string, database_name)
    elif direction == "down":
        for migration_name in reversed(MIGRATIONS):
            module = import_module(f"migrations.{migration_name}")
            print(f"Running migration: {migration_name} (down)")
            await module.downgrade(connection_string, database_name)
    else:
        print(f"Unknown direction: {direction}. Use 'up' or 'down'.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    direction = sys.argv[1]
    asyncio.run(run_migrations(direction))
