#!/usr/bin/env python3
"""One-off interactive phone-code login to mint a Telethon session on the user's
real account (used for the live end-to-end test, since this Mac has the native
Telegram app rather than Telegram Desktop tdata for OpenTele to read).

Two steps so the code can be provided out-of-band:

  request : send_code_request(phone) -> saves temp session + phone_code_hash
  signin  : sign_in(code[, password]) -> saves the final session to SESSION_FILE

Env: API_ID, API_HASH, PHONE, SESSION_FILE, CODE (signin), PASSWORD (signin, 2FA).
"""
import asyncio
import json
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
PHONE = os.environ.get("PHONE", "")
SESSION_FILE = os.environ["SESSION_FILE"]
TMP = SESSION_FILE + ".login"  # holds {session, phone_code_hash} between steps


async def request():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    sent = await client.send_code_request(PHONE)
    with open(TMP, "w") as f:
        json.dump({"session": client.session.save(), "phone_code_hash": sent.phone_code_hash}, f)
    await client.disconnect()
    print("CODE_SENT")


async def signin():
    with open(TMP) as f:
        state = json.load(f)
    client = TelegramClient(StringSession(state["session"]), API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(PHONE, os.environ["CODE"], phone_code_hash=state["phone_code_hash"])
    except SessionPasswordNeededError:
        pwd = os.environ.get("PASSWORD")
        if not pwd:
            print("PASSWORD_REQUIRED")
            await client.disconnect()
            return
        await client.sign_in(password=pwd)
    me = await client.get_me()
    with open(SESSION_FILE, "w") as f:
        f.write(client.session.save())
    try:
        os.remove(TMP)
    except OSError:
        pass
    await client.disconnect()
    print(json.dumps({"ok": True, "id": me.id, "username": me.username, "first_name": me.first_name}))


async def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "request"
    await (request() if step == "request" else signin())


if __name__ == "__main__":
    asyncio.run(main())
