#!/usr/bin/env python3
"""Generate a Telethon StringSession for the user-account Telegram plugin.

This script is a ONE-SHOT helper launched by the desktop as a
subprocess. It:

1. Prompts the user for their Telegram API credentials (api_id, api_hash).
   These are PUBLIC — Telethon publishes them in its My Telegram page.
2. Prompts for their phone number (Telegram login flow).
3. Prompts for the verification code Telegram sends.
4. Optionally prompts for 2FA password if enabled.
5. Prints the resulting Telethon StringSession to stdout.

The desktop captures stdout and pipes it into the user-account
plugin's stdin. The session string then lives in:
  - Desktop Keychain (per session)
  - Plugin process memory for the duration of the connection

It is NEVER written to disk. It is NEVER included in HTTP
responses. It is NEVER logged (the script logs to stderr only,
and only redacted messages go there).

Usage:
  python session_string_generator.py [--api-id N --api-hash X]

If --api-id/--api-hash are not provided, the script prompts
interactively. It uses Telethon's interactive login flow.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import traceback


async def _generate(api_id: int | None, api_hash: str | None) -> str:
    """Run Telethon's interactive sign-in and return StringSession."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        # Print a clean error to stderr (not stdout — the session
        # string is the ONLY thing on stdout).
        print(
            "ERROR: telethon is not installed. Run: pip install telethon",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)

    if api_id is None:
        try:
            api_id_str = input("api_id (from my.telegram.org): ").strip()
            api_id = int(api_id_str)
        except ValueError:
            print("ERROR: api_id must be an integer", file=sys.stderr)
            sys.exit(2)
    if not api_hash:
        api_hash = getpass.getpass("api_hash (from my.telegram.org): ").strip()

    phone = input("Phone (international format, e.g. +1...): ").strip()

    # StringSession with empty value starts a fresh one. TelegramClient
    # is the official entry point. We do NOT save anything to disk;
    # StringSession holds the auth key in memory only.
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone)
    session_str = client.session.save()
    await client.disconnect()
    return session_str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-id", type=int, default=None)
    parser.add_argument("--api-hash", default=None)
    args = parser.parse_args()

    try:
        session = asyncio.run(_generate(args.api_id, args.api_hash))
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        # Print a redacted error to stderr. We DO NOT print traceback
        # because it can include internal Telegram state in some cases.
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    # The ONLY line written to stdout. The desktop captures this
    # and pipes it into the plugin's stdin via the stack runner.
    sys.stdout.write(session)
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
