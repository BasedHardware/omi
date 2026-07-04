#!/usr/bin/env python3
"""Generate a Telethon StringSession for the user-account Telegram plugin.

This script is a ONE-SHOT helper launched by the desktop via
Terminal.app. It guides the user through an interactive sign-in flow:

1. Prompts for api_id + api_hash (from my.telegram.org/apps)
2. Prompts for phone number
3. Prompts for the verification code Telegram sends
4. Optionally prompts for 2FA password
5. Writes the resulting StringSession to --output-file

The desktop opens Terminal.app with this script, the user interacts
in the Terminal window, and the session is written to a temp file.
The desktop reads the temp file and saves the session to Keychain.

Usage:
  python session_string_generator.py [--api-id N --api-hash X] [--output-file PATH]

If --output-file is set: interactive prompts go to stdout/stderr
(visible in Terminal), session goes to the file.
If --output-file is NOT set: session goes to stdout (legacy mode).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys


async def _generate(api_id: int | None, api_hash: str | None) -> str:
    """Run Telethon's interactive sign-in and return StringSession."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print(
            "ERROR: telethon is not installed. Run: pip install telethon",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)

    print("", file=sys.stderr, flush=True)
    print("=" * 60, file=sys.stderr, flush=True)
    print("  Omi AI Clone — Telegram Session Setup", file=sys.stderr, flush=True)
    print("=" * 60, file=sys.stderr, flush=True)
    print("", file=sys.stderr, flush=True)
    print("This will sign you into your personal Telegram account", file=sys.stderr, flush=True)
    print("so Omi can reply to messages as you.", file=sys.stderr, flush=True)
    print("", file=sys.stderr, flush=True)

    if api_id is None:
        print("Get your api_id and api_hash from: https://my.telegram.org/apps", file=sys.stderr, flush=True)
        print("", file=sys.stderr, flush=True)
        try:
            api_id_str = input("api_id (from my.telegram.org): ").strip()
            api_id = int(api_id_str)
        except ValueError:
            print("ERROR: api_id must be an integer", file=sys.stderr, flush=True)
            sys.exit(2)
    if not api_hash:
        api_hash = getpass.getpass("api_hash (from my.telegram.org): ").strip()

    print("", file=sys.stderr, flush=True)
    phone = input("Phone (international format, e.g. +66...): ").strip()

    print("", file=sys.stderr, flush=True)
    print("Connecting to Telegram...", file=sys.stderr, flush=True)

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(phone=phone)

    # Fetch user info BEFORE disconnecting — Telethon API calls
    # require an active connection. cubic review 4629894864 P1:
    # get_me() after disconnect() raises ConnectionError.
    me = await client.get_me()
    name = " ".join(filter(None, [getattr(me, "first_name", None), getattr(me, "last_name", None)]))

    session_str = client.session.save()
    await client.disconnect()

    print("", file=sys.stderr, flush=True)
    print(f"Signed in successfully as {name}!", file=sys.stderr, flush=True)
    print("Remember to not break the ToS or you will risk an account ban!", file=sys.stderr, flush=True)

    return session_str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-id", type=int, default=None)
    parser.add_argument("--api-hash", default=None)
    parser.add_argument(
        "--output-file",
        default=None,
        help="Write the session string to this file instead of stdout.",
    )
    args = parser.parse_args()

    try:
        session = asyncio.run(_generate(args.api_id, args.api_hash))
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return 1

    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(session)
        print(f"\nSession written to file successfully.", file=sys.stderr, flush=True)
    else:
        sys.stdout.write(session)
        sys.stdout.write("\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
