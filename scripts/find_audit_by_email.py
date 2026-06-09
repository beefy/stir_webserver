"""
Script to find all audit records for a given email address.

The email is anonymized using SHA-256 (same algorithm as
``app.utils.anonymize_email``), so this script hashes the provided email
and searches the audits collection for matching records.

Usage:
    PYTHONPATH=. python scripts/find_audit_by_email.py <email>

Environment variables:
    MONGODB_CONNECTION_STRING: MongoDB connection string
        (default: mongodb://localhost:27017)
    MONGODB_DATABASE_NAME: Database name
        (default: stir_webserver)
"""

import asyncio
import hashlib
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


def anonymize_email(email: str | None) -> str | None:
    """Deterministically anonymize an email using SHA-256.

    Mirrors ``app.utils.anonymize_email`` so the lookup hash matches
    what the application stores.
    """
    if email is None:
        return None
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
    return f"email_anon_{digest[:16]}"


async def main() -> None:
    """Query the audits collection for records matching the given email."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    raw_email = sys.argv[1]
    email_anon = anonymize_email(raw_email)

    if email_anon is None:
        print("Error: cannot anonymize empty email.")
        sys.exit(1)

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
    collection = database["audits"]

    cursor = collection.find(
        {"user_email_anon": email_anon},
    ).sort("request_datetime", -1)

    count = 0
    async for doc in cursor:
        count += 1
        print(
            f"audit_id:              {doc.get('audit_id')}\n"
            f"request_type:          {doc.get('request_type')}\n"
            f"user_id:               {doc.get('user_id')}\n"
            f"user_email_anon:       {doc.get('user_email_anon')}\n"
            f"id_verification_method:{doc.get('id_verification_method')}\n"
            f"request_datetime:      {doc.get('request_datetime')}\n"
            f"finish_datetime:       {doc.get('finish_datetime')}\n"
            f"outcome:               {doc.get('outcome')}\n"
            f"{'-' * 60}"
        )

    print(f"\nTotal audit records for '{raw_email}': {count}")


if __name__ == "__main__":
    asyncio.run(main())
