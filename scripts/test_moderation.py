"""
Script to test the DeepSeek moderation API with a given message text.

Usage:
    PYTHONPATH=. python scripts/test_moderation.py "Your message text here"

Requires DEEPSEEK_API_KEY to be set in the environment or .env file.

Examples:
    PYTHONPATH=. python scripts/test_moderation.py "Hello, how are you?"
    PYTHONPATH=. python scripts/test_moderation.py "I'm going to hurt you"
    PYTHONPATH=. python scripts/test_moderation.py \
        "Check out this great product at https://spam.example.com"
"""

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


async def test_moderation(message_content: str) -> None:
    """Send a message to DeepSeek and print the raw response."""
    if not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY is not set.")
        print(
            "Set it in your .env file or export it as an "
            "environment variable."
        )
        sys.exit(1)

    print(f"Testing moderation on: \"{message_content}\"")
    print(f"Calling DeepSeek API at {DEEPSEEK_API_URL}...")
    print()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a content moderation assistant. "
                                "Respond only in JSON with either "
                                '{"moderation_action": "ban"} or '
                                '{"moderation_action": "dismiss"}. '
                                'Respond with {"moderation_action": "ban"} '
                                "if the message content contains hate speech, "
                                "harassment, explicit content, calls for "
                                "violence, or anything else that you think "
                                "would qualify banning a user. "
                                'Otherwise, respond with '
                                '{"moderation_action": "dismiss"}.'
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Moderate this message: {message_content}"
                            ),
                        },
                    ],
                    "max_tokens": 50,
                },
            )
            response.raise_for_status()
            data = response.json()

            print("=== Raw API Response ===")
            print(json.dumps(data, indent=2))
            print()

            # Extract and parse the moderation result
            content = data["choices"][0]["message"]["content"].strip()
            print("=== Model Response Content ===")
            print(content)
            print()

            try:
                parsed = json.loads(content)
                action = parsed.get("moderation_action")
                print(f"Parsed moderation_action: {action}")
                if action == "ban":
                    print(">>> RESULT: BAN (user would be shadow-banned)")
                elif action == "dismiss":
                    print(">>> RESULT: DISMISS (no action taken)")
                else:
                    print(f">>> RESULT: UNEXPECTED VALUE ('{action}')")
            except json.JSONDecodeError as e:
                print(f">>> RESULT: NOT VALID JSON — {e}")

    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code}")
        print(e.response.text)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    asyncio.run(test_moderation(message))
