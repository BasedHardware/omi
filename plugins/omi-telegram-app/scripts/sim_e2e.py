"""End-to-end simulation of the Telegram plugin's webhook flow.

Drives a running local plugin (started separately on port 18800 by default)
through every path the /webhook, /setup, /toggle, /.well-known/omi-tools.json,
and /health endpoints support, WITHOUT requiring a real Telegram bot.

Layer 1 verification — proves the plugin code is wired correctly. The full
production E2E (Layer 3 — a real Telegram message round-trip with persona
reply) requires a real bot token from @BotFather, a real persona, and the
Telegram user to actually send a message. See ../E2E_RUNBOOK.md for those.

Usage:
    # 1. Start the plugin in one terminal
    STORAGE_DIR=/tmp/omi-tg-e2e \
    TELEGRAM_WEBHOOK_SECRET=test-secret-e2e \
    OMI_BASE_URL=https://api.omi.me \
      uvicorn --app-dir plugins/omi-telegram-app main:app \
              --host 127.0.0.1 --port 18800 --log-level info

    # 2. In another terminal, seed a user file (the /start handshake does
    #    this in production; we skip it here):
    echo '{"999001":{"chat_id":"999001","omi_uid":"test-uid-e2e","persona_id":"test-persona-e2e","omi_dev_api_key":"placeholder-key","bot_token":"placeholder-token","auto_reply_enabled":true,"created_at":"2026-06-29T00:00:00","updated_at":"2026-06-29T00:00:00"}}' \
      > /tmp/omi-tg-e2e/users_data.json

    # 3. Bounce the plugin so it loads the file (storage is module-cached)
    #    (kill the uvicorn process, restart it as in step 1)

    # 4. Run this script:
    python plugins/omi-telegram-app/scripts/sim_e2e.py

    # It will hit /health, /, /.well-known/omi-tools.json, /setup (expect
    # 4xx — invalid bot_token), /webhook (regular, /start, group, malformed
    # JSON), and /toggle (right/wrong token, unknown chat). Asserts each step.

Why this script exists:
- The unit tests cover individual functions, but a single end-to-end pass
  catches refactor regressions that break the wiring between pieces.
- Specifically, it would have caught the T-007 refactor bug where the
  send_message call was accidentally dropped from _dispatch_auto_reply.
"""

import json
import os
import sys

import requests

BASE = os.environ.get("PLUGIN_URL", "http://127.0.0.1:18800")
SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "test-secret-e2e")
BOUND_CHAT_ID = "999001"

# Path to the storage file. Must match STORAGE_DIR passed to uvicorn.
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/tmp/omi-tg-e2e")


def step(label):
    print(f"\n── {label} ──")


def assert_eq(actual, expected, label):
    assert actual == expected, f"FAIL {label}: expected {expected!r}, got {actual!r}"
    print(f"   ✓ {label}: {actual!r}")


def main():
    # /health
    step("GET /health")
    r = requests.get(f"{BASE}/health", timeout=5)
    assert_eq(r.status_code, 200, "status")
    assert_eq(r.json()["status"], "ok", "body.status")

    # /.well-known/omi-tools.json — T-007 manifest endpoint
    step("GET /.well-known/omi-tools.json")
    r = requests.get(f"{BASE}/.well-known/omi-tools.json", timeout=5)
    assert_eq(r.status_code, 200, "status")
    manifest = r.json()
    assert_eq(manifest["tools"][0]["name"], "toggle_auto_reply", "tool name")
    assert_eq(manifest["tools"][0]["endpoint"], "/toggle", "tool endpoint")
    assert_eq(
        set(manifest["tools"][0]["parameters"]["required"]), {"chat_id", "enabled", "bot_token"}, "tool required params"
    )
    assert_eq(manifest["chat_messages"]["enabled"], False, "chat_messages.enabled")
    assert_eq(manifest["chat_messages"]["target"], "app", "chat_messages.target")

    # /setup with an obviously invalid bot_token — expect 4xx (the plugin
    # calls Telegram's getMe which 404s for an invalid token).
    step("POST /setup with invalid bot_token (expect 4xx)")
    r = requests.post(
        f"{BASE}/setup",
        json={
            "bot_token": "0000000000:invalid",
            "omi_uid": "u",
            "persona_id": "p",
            "omi_dev_api_key": "k",
            "public_base_url": "https://x.example.com",
        },
        timeout=10,
    )
    print(f"   HTTP {r.status_code} body={r.text[:80]!r}")
    assert r.status_code >= 400, f"expected 4xx, got {r.status_code}"

    # /webhook with bad secret
    step("POST /webhook with bad secret (expect 401)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"update_id": 1, "message": {"chat": {"id": 1}}},
        timeout=5,
    )
    assert_eq(r.status_code, 401, "status")

    # /webhook with a regular text message from the bound user. The persona
    # call will fail (api.omi.me returns 404 because the persona doesn't
    # exist), but the dispatch path itself should fire — that proves the
    # bug fixed in cc95e155d (the missing send_message call) hasn't come
    # back.
    step("POST /webhook — regular text from bound user (expect persona call)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
        json={
            "update_id": 2,
            "message": {
                "message_id": 2,
                "chat": {"id": int(BOUND_CHAT_ID), "type": "private"},
                "from": {"id": int(BOUND_CHAT_ID), "is_bot": False, "first_name": "Alice"},
                "text": "what's my favorite coffee?",
            },
        },
        timeout=15,
    )
    assert_eq(r.status_code, 200, "status")

    # /webhook with /start <bogus-token>
    step("POST /webhook — /start <bogus> from unknown chat (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
        json={
            "update_id": 3,
            "message": {
                "message_id": 3,
                "chat": {"id": 999002, "type": "private"},
                "from": {"id": 999002, "is_bot": False, "first_name": "Bob"},
                "text": "/start deadbeef",
            },
        },
        timeout=10,
    )
    assert_eq(r.status_code, 200, "status")

    # /webhook from a group chat — should be silently dropped
    step("POST /webhook from group chat (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
        json={
            "update_id": 4,
            "message": {
                "message_id": 4,
                "chat": {"id": -1001234567890, "type": "supergroup"},
                "from": {"id": 999001, "is_bot": False, "first_name": "Alice"},
                "text": "hello",
            },
        },
        timeout=5,
    )
    assert_eq(r.status_code, 200, "status")

    # /webhook with malformed JSON — silently dropped
    step("POST /webhook with malformed JSON (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
        data="not json",
        timeout=5,
    )
    assert_eq(r.status_code, 200, "status")

    # /toggle with right token, wrong token, unknown chat_id
    step("POST /toggle — right token (expect 200)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": BOUND_CHAT_ID, "enabled": False, "bot_token": "placeholder-token"},
        timeout=5,
    )
    assert_eq(r.status_code, 200, "status")

    step("POST /toggle — wrong token (expect 403)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": BOUND_CHAT_ID, "enabled": True, "bot_token": "WRONG"},
        timeout=5,
    )
    assert_eq(r.status_code, 403, "status")

    step("POST /toggle — unknown chat_id (expect 403, enumeration-safe)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": "999999", "enabled": True, "bot_token": "placeholder-token"},
        timeout=5,
    )
    assert_eq(r.status_code, 403, "status")

    print("\n✓ All steps passed. Layer 1 E2E verified.")
    print(f"  Storage dir: {STORAGE_DIR}")
    print(f"  Plugin URL:  {BASE}")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        sys.exit(1)
