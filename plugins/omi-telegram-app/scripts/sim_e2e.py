"""End-to-end simulation of the Telegram plugin's webhook flow.

Drives a running local plugin (started separately on port 18800 by default)
through every path the /webhook, /setup, /toggle, /.well-known/omi-tools.json,
and /health endpoints support, WITHOUT requiring a real Telegram bot.

Layer 1 verification — proves the plugin code is wired correctly. The full
production E2E (Layer 3 — a real Telegram message round-trip with persona
reply) requires a real bot token from @BotFather, a real persona, and the
Telegram user to actually send a message. See ../E2E_RUNBOOK.md for those.

Usage:
    # 1. Start the plugin in one terminal (export the var so step 2
    #    can reuse it without re-deriving the path).
    export STORAGE_DIR=/tmp/omi-tg-e2e
    export TELEGRAM_WEBHOOK_SECRET=test-secret-e2e
    export OMI_BASE_URL=https://api.omi.me
    mkdir -p "$STORAGE_DIR"
    uvicorn --app-dir plugins/omi-telegram-app main:app \
            --host 127.0.0.1 --port 18800 --log-level info \
            > "$STORAGE_DIR/plugin.log" 2>&1 &

    # 2. In another terminal, seed a user file (the /start handshake
    #    does this in production; we skip it here). Use the same
    #    absolute path that step 1 used — the script's log-tailing
    #    depends on $STORAGE_DIR being set in BOTH terminals.
    echo '{"999001":{"chat_id":"999001","omi_uid":"test-uid-e2e","persona_id":"test-persona-e2e","omi_dev_api_key":"placeholder-key","bot_token":"placeholder-token","auto_reply_enabled":true,"created_at":"2026-06-29T00:00:00","updated_at":"2026-06-29T00:00:00"}}' \
      > "$STORAGE_DIR/users_data.json"

    # 3. Bounce the plugin so it loads the file (storage is module-cached)
    #    (kill the uvicorn process, restart it as in step 1)

    # 4. Run this script from the repo root:
    python plugins/omi-telegram-app/scripts/sim_e2e.py

The script's critical dispatch assertion tails $STORAGE_DIR/plugin.log
to verify both the persona POST and the sendMessage POST fired. Without
the `> "$STORAGE_DIR/plugin.log"` redirect in step 1, the file won't
exist (the plugin uses stdout-only logging) and the assertion fails.
Identified by cubic (P1) on PR #8531.

Why this script exists:
- The unit tests cover individual functions, but a single end-to-end pass
  catches refactor regressions that break the wiring between pieces.
- The dispatch assertion (step: regular-message webhook) tails the plugin
  log and asserts that BOTH the persona call AND the send_message call
  fired. Without the log check, a regression that drops the send_message
  call (cc95e155d was exactly this) would slip past, because /webhook
  still returns 200. Reviewers identified this gap (cubic); the log check
  is what makes the assertion real.

The script uses explicit sys.exit() instead of `assert` because
`python -O` strips assertions and would cause silent false passes.
"""

import json
import os
import re
import sys
import time

import requests

BASE = os.environ.get("PLUGIN_URL", "http://127.0.0.1:18800")
SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "test-secret-e2e")
BOUND_CHAT_ID = "999001"
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/tmp/omi-tg-e2e")
PLUGIN_LOG = os.environ.get("PLUGIN_LOG", f"{STORAGE_DIR}/plugin.log")

# Exit codes (independent of assert so they survive `python -O`).
EXIT_OK = 0
EXIT_STEP_FAIL = 1
EXIT_DISPATCH_FAIL = 2


def step(label):
    print(f"\n── {label} ──")


def check(actual, expected, label):
    """Equality check that exits with a clear message on mismatch."""
    if actual != expected:
        print(f"   ✗ FAIL {label}: expected {expected!r}, got {actual!r}", file=sys.stderr)
        sys.exit(EXIT_STEP_FAIL)
    print(f"   ✓ {label}: {actual!r}")


def tail_log_for(predicate, *, timeout=15.0, poll=0.5, since=None):
    """Block until `predicate(line)` returns True for some new log line.

    Returns the matching line (or None if timeout). `since` is the byte
    offset to start reading from — pass the file size from before the
    action you want to observe.
    """
    if not os.path.exists(PLUGIN_LOG):
        # P1 (cubic): the script's success criterion depends on this
        # file existing. If it doesn't, the dispatcher may STILL be
        # working — the user just didn't redirect uvicorn's output
        # to plugin.log. Give them an actionable message instead of
        # the generic 'sendMessage never appeared'.
        print(
            f"   ✗ FAIL plugin log not found at {PLUGIN_LOG}. "
            f"Start the plugin with stdout/stderr redirected to that "
            f"file (see step 1 in this script's docstring).",
            file=sys.stderr,
        )
        sys.exit(EXIT_DISPATCH_FAIL)
    with open(PLUGIN_LOG, "rb") as f:
        if since is not None:
            f.seek(since)
        else:
            f.seek(0, os.SEEK_END)
        end_at = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < end_at:
            chunk = f.read()
            if chunk:
                buf += chunk
                for line in buf.splitlines():
                    if predicate(line.decode("utf-8", errors="replace")):
                        return line.decode("utf-8", errors="replace")
                # keep tail of partial last line
                buf = buf.split(b"\n", -1)[-1] if b"\n" in buf else buf
            time.sleep(poll)
    return None


def main():
    # /health
    step("GET /health")
    r = requests.get(f"{BASE}/health", timeout=5)
    check(r.status_code, 200, "status")
    check(r.json()["status"], "ok", "body.status")

    # /.well-known/omi-tools.json — T-007 manifest endpoint
    step("GET /.well-known/omi-tools.json")
    r = requests.get(f"{BASE}/.well-known/omi-tools.json", timeout=5)
    check(r.status_code, 200, "status")
    manifest = r.json()
    check(manifest["tools"][0]["name"], "toggle_auto_reply", "tool name")
    check(manifest["tools"][0]["endpoint"], "/toggle", "tool endpoint")
    check(
        set(manifest["tools"][0]["parameters"]["required"]),
        {"chat_id", "enabled", "bot_token"},
        "tool required params",
    )
    check(manifest["chat_messages"]["enabled"], False, "chat_messages.enabled")
    check(manifest["chat_messages"]["target"], "app", "chat_messages.target")

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
    if r.status_code < 400:
        print(f"   ✗ FAIL expected 4xx, got {r.status_code}", file=sys.stderr)
        sys.exit(EXIT_STEP_FAIL)

    # /webhook with bad secret
    step("POST /webhook with bad secret (expect 401)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"update_id": 1, "message": {"chat": {"id": 1}}},
        timeout=5,
    )
    check(r.status_code, 401, "status")

    # ------------------------------------------------------------------
    # Dispatch path — THE critical regression check.
    #
    # We have to verify TWO things, not one:
    #   (a) the persona call fires
    #   (b) the send_message call fires
    #
    # (a) without (b) is exactly the regression fixed in cc95e155d —
    # _dispatch_auto_reply returned silently without calling
    # send_message. (b) without (a) would mean the plugin sent a reply
    # without consulting the persona. We need both.
    #
    # HTTP 200 from /webhook is NOT a sufficient check — the webhook
    # returns 200 in every success path, including when the dispatch
    # function is broken. So we additionally tail the plugin log and
    # assert that BOTH:
    #   - "POST .../v2/integrations/.../persona-chat" appears, AND
    #   - "POST .../api.telegram.org/bot.../sendMessage" appears
    #
    # If send_message is missing from _dispatch_auto_reply, the second
    # pattern won't appear and this step exits non-zero.
    # ------------------------------------------------------------------
    step("POST /webhook — regular text from bound user (assert dispatch fires)")
    log_offset = os.path.getsize(PLUGIN_LOG) if os.path.exists(PLUGIN_LOG) else 0
    r = requests.post(
        f"{BASE}/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": SECRET,
            "Content-Type": "application/json",
        },
        json={
            "update_id": 2,
            "message": {
                "message_id": 2,
                "chat": {"id": int(BOUND_CHAT_ID), "type": "private"},
                "from": {
                    "id": int(BOUND_CHAT_ID),
                    "is_bot": False,
                    "first_name": "Alice",
                },
                "text": "what's my favorite coffee?",
            },
        },
        timeout=15,
    )
    check(r.status_code, 200, "/webhook status")

    # Now wait for the persona POST and the sendMessage POST to appear in
    # the log. We give it 15s — the persona call is the slow one.
    persona_match = tail_log_for(
        lambda line: "/user/persona-chat" in line,
        timeout=15.0,
        since=log_offset,
    )
    send_match = tail_log_for(
        lambda line: re.search(r"/bot\S+/sendMessage", line) is not None,
        timeout=10.0,
        since=log_offset,
    )

    if persona_match is None:
        print(
            "   ✗ FAIL persona call never appeared in plugin log — "
            "_dispatch_auto_reply didn't run (or persona endpoint is wrong)",
            file=sys.stderr,
        )
        sys.exit(EXIT_DISPATCH_FAIL)
    print(f"   ✓ persona call observed: {persona_match.strip()[:90]}…")

    if send_match is None:
        print(
            "   ✗ FAIL sendMessage never appeared in plugin log — "
            "this is the regression fixed in cc95e155d. "
            "_dispatch_auto_reply returned without calling send_message.",
            file=sys.stderr,
        )
        sys.exit(EXIT_DISPATCH_FAIL)
    # Redact the bot token from the matched URL before printing — the
    # Telegram Bot API URL contains "/bot<TOKEN>/sendMessage" and the
    # raw token is a secret. P2 (cubic) on PR #8531.
    redacted = re.sub(r"/bot[^/\s]+/sendMessage", "/bot<REDACTED>/sendMessage", send_match.strip())
    print(f"   ✓ sendMessage observed: {redacted[:90]}…")

    # /webhook with /start <bogus-token>
    step("POST /webhook — /start <bogus> from unknown chat (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": SECRET,
            "Content-Type": "application/json",
        },
        json={
            "update_id": 3,
            "message": {
                "message_id": 3,
                "chat": {"id": 999002, "type": "private"},
                "from": {
                    "id": 999002,
                    "is_bot": False,
                    "first_name": "Bob",
                },
                "text": "/start deadbeef",
            },
        },
        timeout=10,
    )
    check(r.status_code, 200, "status")

    # /webhook from a group chat — should be silently dropped
    step("POST /webhook from group chat (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": SECRET,
            "Content-Type": "application/json",
        },
        json={
            "update_id": 4,
            "message": {
                "message_id": 4,
                "chat": {"id": -1001234567890, "type": "supergroup"},
                "from": {
                    "id": 999001,
                    "is_bot": False,
                    "first_name": "Alice",
                },
                "text": "hello",
            },
        },
        timeout=5,
    )
    check(r.status_code, 200, "status")

    # /webhook with malformed JSON — silently dropped
    step("POST /webhook with malformed JSON (expect silent drop)")
    r = requests.post(
        f"{BASE}/webhook",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": SECRET,
            "Content-Type": "application/json",
        },
        data="not json",
        timeout=5,
    )
    check(r.status_code, 200, "status")

    # /toggle with right token, wrong token, unknown chat_id
    step("POST /toggle — right token (expect 200)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": BOUND_CHAT_ID, "enabled": False, "bot_token": "placeholder-token"},
        timeout=5,
    )
    check(r.status_code, 200, "status")

    step("POST /toggle — wrong token (expect 403)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": BOUND_CHAT_ID, "enabled": True, "bot_token": "WRONG"},
        timeout=5,
    )
    check(r.status_code, 403, "status")

    step("POST /toggle — unknown chat_id (expect 403, enumeration-safe)")
    r = requests.post(
        f"{BASE}/toggle",
        json={"chat_id": "999999", "enabled": True, "bot_token": "placeholder-token"},
        timeout=5,
    )
    check(r.status_code, 403, "status")

    print("\n✓ All steps passed. Layer 1 E2E verified.")
    print(f"  Storage dir: {STORAGE_DIR}")
    print(f"  Plugin URL:  {BASE}")
    print(f"  Plugin log:  {PLUGIN_LOG}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n✗ UNCAUGHT: {e!r}", file=sys.stderr)
        sys.exit(EXIT_STEP_FAIL)
