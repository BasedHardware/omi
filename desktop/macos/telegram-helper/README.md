# Omi Telegram helper

On-device MTProto client for the Telegram "reply on my behalf" feature. Runs as a
long-lived subprocess of the macOS app, speaking newline-delimited JSON over
stdio. See the module docstring in `omi_telegram_helper.py` for the full command
and event protocol.

## Why this exists

Telegram — unlike iMessage — has **no local message database**. `chat.db` is
plaintext SQLite; Telegram Desktop's `tdata` is encrypted and holds no chat
history, only the auth session. So reading and sending must go over MTProto.
[OpenTele](https://opentele.readthedocs.io/) converts the already-logged-in
Telegram Desktop `tdata` into a [Telethon](https://docs.telethon.dev/) session (no
phone-code login), and Telethon provides event-driven near-real-time read + send.

The session string is written to `--session-file` (kept under the app's Application
Support dir) and **never leaves the user's Mac**.

## Run locally (dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Protocol smoke test — no Telegram/network:
printf '%s\n' '{"cmd":"ping"}' '{"cmd":"emit_fake"}' '{"cmd":"shutdown"}' \
  | python3 omi_telegram_helper.py --selftest
# Real run (needs Telegram Desktop logged in on this Mac):
python3 omi_telegram_helper.py --api-id "$API_ID" --api-hash "$API_HASH" \
  --session-file /tmp/omi-tg.session
```

## Build the shipped binary

```bash
./build.sh   # -> dist/omi-telegram-helper (PyInstaller onefile)
```

CI (Codemagic) builds, signs, and notarizes this alongside the app. The app
bundles it into Resources and launches it via `TelegramClientService`.

## `--selftest`

Drives the exact stdio protocol with fake, deterministic events and **no Telegram
or network** — used to integration-test the Swift `TelegramClientService`/inbox
flow without real credentials. `{"cmd":"emit_fake","text":"…"}` synthesizes an
incoming `new_message`.
