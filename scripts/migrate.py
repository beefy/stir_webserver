"""
Migration runner for Beanie ODM migrations.

Usage:
    python scripts/migrate.py [up|down]

Requires PYTHONPATH to include the project root, e.g.:
    PYTHONPATH=. python scripts/migrate.py up

Environment variables:
    MONGODB_CONNECTION_STRING: MongoDB connection string
        (default: mongodb://localhost:27017)
    MONGODB_DATABASE_NAME: Database name
        (default: stir_webserver)
"""

import asyncio
import os
import re
import sys
from importlib import import_module
from pathlib import Path


def _discover_migrations() -> list[str]:
    """Discover migration modules in the migrations/ directory.

    Scans for Python files matching the pattern ``NNN_*.py`` and returns
    them sorted by their numeric prefix.
    """
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    pattern = re.compile(r"^(\d+)_(.+)\.py$")

    entries: list[tuple[int, str]] = []
    for child in migrations_dir.iterdir():
        if child.is_file() and (m := pattern.match(child.name)):
            entries.append((int(m.group(1)), child.stem))

    entries.sort(key=lambda x: x[0])
    return [name for _, name in entries]


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

    migrations = _discover_migrations()
    if not migrations:
        print("No migrations found.")
        return

    if direction == "up":
        for migration_name in migrations:
            module = import_module(f"migrations.{migration_name}")
            print(f"Running migration: {migration_name} (up)")
            await module.upgrade(connection_string, database_name)
    elif direction == "down":
        for migration_name in reversed(migrations):
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
