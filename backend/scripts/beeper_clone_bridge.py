#!/usr/bin/env python3
"""Beeper <-> Omi AI clone bridge (reference implementation).

Runs on the user's machine next to Beeper Desktop, whose local API exposes every
connected chat network (WhatsApp / Telegram / iMessage / Signal / ...). For each
incoming message the bridge:

  1. reads the recent thread with that contact from Beeper,
  2. asks the Omi backend to draft a reply AS the user (POST /v1/clone/reply),
  3. decides locally whether to auto-send via Beeper or queue the draft for the
     user to review in the desktop app.

The Beeper access token never leaves the machine. The backend owns the non-negotiable
safety floor and only returns a verdict (meets_safety_floor); it never certifies auto-send.
Auto-send is the operator's LOCAL decision and requires ALL of: CLONE_MODE=auto, the contact
on the local CLONE_ALLOWLIST, outside local CLONE_QUIET_HOURS, and the backend reporting
meets_safety_floor=true (not sensitive, no injection, confidence above the server floor). The
allowlist and mode are local operator policy and are never sent to the backend, so a token
holder cannot ask the backend to certify a send. In the default review mode everything is
queued for the user to approve in the desktop app.

Env:
  BEEPER_ACCESS_TOKEN   Beeper Desktop API token (required)
  OMI_API_BASE_URL      Omi backend base URL (default https://api.omi.me)
  OMI_AUTH_TOKEN        Firebase ID token for the Omi user (required)
  CLONE_MODE            "review" (default) or "auto" (local operator policy)
  CLONE_ALLOWLIST       comma-separated Beeper chat ids allowed to auto-reply (local policy)
  CLONE_QUIET_HOURS     optional local quiet window "START-END" in 24h hours (e.g. "22-7");
                        auto-send is suppressed inside it
  CLONE_REVIEW_QUEUE    path to append review drafts as JSON lines
                        (default: ~/.omi/clone_review_queue.jsonl)

Beeper CLI is used for portability (no SDK dependency); see
https://developers.beeper.com/desktop-api-reference/cli
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

OMI_API_BASE_URL = os.environ.get("OMI_API_BASE_URL", "https://api.omi.me").rstrip("/")
OMI_AUTH_TOKEN = os.environ.get("OMI_AUTH_TOKEN", "")
CLONE_MODE = os.environ.get("CLONE_MODE", "review").strip().lower()
CLONE_ALLOWLIST = [c.strip() for c in os.environ.get("CLONE_ALLOWLIST", "").split(",") if c.strip()]
CLONE_QUIET_HOURS = os.environ.get("CLONE_QUIET_HOURS", "").strip()
CLONE_REVIEW_QUEUE = Path(os.environ.get("CLONE_REVIEW_QUEUE", str(Path.home() / ".omi" / "clone_review_queue.jsonl")))

# Bounded dedup so a replayed/duplicate watch event isn't drafted (and possibly
# auto-sent) twice.
_MAX_SEEN_EVENTS = 1024
_seen_event_keys: Deque[str] = deque()
_seen_event_set: Set[str] = set()


def _is_duplicate(key: str) -> bool:
    """Read-only check; does not record the key (so a failed attempt can retry)."""
    return key in _seen_event_set


def _mark_handled(key: str) -> None:
    """Commit a key as handled. Called only after a reply was successfully queued or
    sent, so a transient failure doesn't permanently drop the message on replay."""
    if key in _seen_event_set:
        return
    _seen_event_set.add(key)
    _seen_event_keys.append(key)
    if len(_seen_event_keys) > _MAX_SEEN_EVENTS:
        _seen_event_set.discard(_seen_event_keys.popleft())


def _api_base_url_error() -> Optional[str]:
    """Reject a non-TLS backend URL so the auth token and message content are never
    sent in cleartext to an env-overridden or malicious host."""
    parsed = urllib.parse.urlparse(OMI_API_BASE_URL)
    if parsed.scheme == "https":
        return None
    if parsed.scheme == "http" and (parsed.hostname or "") in {"localhost", "127.0.0.1"}:
        return None
    return (
        f"OMI_API_BASE_URL must be https (or http on localhost); refusing to send credentials to {OMI_API_BASE_URL!r}"
    )


THREAD_LIMIT = 12


def _beeper(args: List[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    """Invoke the `beeper` CLI. Token is passed via env (BEEPER_ACCESS_TOKEN)."""
    return subprocess.run(["beeper", *args], capture_output=capture, text=True, check=False)


def _beeper_json(args: List[str]) -> Any:
    result = _beeper([*args, "--json"])
    if result.returncode != 0:
        raise RuntimeError(f"beeper {' '.join(args)} failed: {result.stderr.strip()}")
    payload = json.loads(result.stdout or "{}")
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def _recent_thread(chat_id: str) -> List[Dict[str, str]]:
    """Recent messages with a contact, oldest first, as {sender: them|me, text}."""
    try:
        messages = _beeper_json(["messages", "list", "--chat", chat_id, "--limit", str(THREAD_LIMIT)])
    except Exception as exc:  # noqa: BLE001 - the thread is best-effort context
        print(f"[clone-bridge] could not load thread for {chat_id}: {exc}", file=sys.stderr)
        return []
    thread: List[Dict[str, str]] = []
    for message in messages if isinstance(messages, list) else []:
        text = (message.get("text") or "").strip()
        if not text:
            continue
        sender = "me" if message.get("isSender") or message.get("is_sender") else "them"
        thread.append({"sender": sender, "text": text})
    return thread[-THREAD_LIMIT:]


def _draft_reply(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    chat_id = str(event.get("chatID") or event.get("chat_id") or "")
    incoming = (event.get("text") or "").strip()
    if not chat_id or not incoming:
        return None

    body = {
        "incoming_message": incoming,
        "contact_id": chat_id,
        "contact_name": event.get("senderName") or event.get("sender_name"),
        "network": event.get("network") or event.get("accountID"),
        "thread": _recent_thread(chat_id),
    }
    request = urllib.request.Request(
        f"{OMI_API_BASE_URL}/v1/clone/reply",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {OMI_AUTH_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - scheme validated https/localhost
        return json.loads(response.read().decode("utf-8"))


def _queue_for_review(chat_id: str, incoming: str, reply: Dict[str, Any]) -> None:
    CLONE_REVIEW_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with CLONE_REVIEW_QUEUE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"chat_id": chat_id, "incoming": incoming, "reply": reply}) + "\n")
    print(f"[clone-bridge] queued draft for review (chat={chat_id}, action={reply.get('action')})")


def _send(chat_id: str, text: str) -> None:
    result = _beeper(["send", "text", "--to", chat_id, "--message", text])
    if result.returncode != 0:
        raise RuntimeError(f"beeper send failed: {result.stderr.strip()}")
    print(f"[clone-bridge] auto-sent reply to {chat_id}")


def _in_local_quiet_hours() -> bool:
    """True if the operator's local time is inside CLONE_QUIET_HOURS ("START-END", 24h hours).
    Auto-send is suppressed during the window; supports wraparound (e.g. "22-7")."""
    if "-" not in CLONE_QUIET_HOURS:
        return False
    start_s, _, end_s = CLONE_QUIET_HOURS.partition("-")
    try:
        start, end = int(start_s) % 24, int(end_s) % 24
    except ValueError:
        return False
    if start == end:
        return False
    hour = datetime.datetime.now().hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _local_auto_send_allowed(chat_id: str, reply: Dict[str, Any]) -> bool:
    """Auto-send only when the operator's LOCAL policy authorizes it AND the backend certified
    the draft cleared its non-negotiable safety floor. Mode, allowlist, and quiet hours are local
    operator policy and are never sent to or trusted from the backend, so a token holder cannot ask
    the backend to certify a send."""
    if CLONE_MODE != "auto":
        return False
    if not reply.get("meets_safety_floor"):
        return False
    if not reply.get("draft"):
        return False
    if _in_local_quiet_hours():
        return False
    allow = {c.strip().lower() for c in CLONE_ALLOWLIST if c.strip()}
    return chat_id.strip().lower() in allow


def _handle_event(event: Dict[str, Any]) -> None:
    # Only react to inbound message events from other people. Require an explicit
    # message type; an untyped/malformed event is ignored rather than trusted.
    if event.get("type") not in {"message", "message.new", "message.upserted"}:
        return
    if event.get("isSender") or event.get("is_sender"):
        return
    chat_id = str(event.get("chatID") or event.get("chat_id") or "")
    incoming = (event.get("text") or "").strip()
    if not chat_id or not incoming:
        return
    # Scope the dedup key with chat_id: Beeper message ids are unique per chat, not
    # globally, so an unscoped id could collide across chats and drop a valid message.
    message_id = event.get("messageID") or event.get("message_id") or event.get("id") or incoming
    dedup_key = f"{chat_id}:{message_id}"
    if _is_duplicate(dedup_key):
        return

    reply = _draft_reply(event)
    if not reply:
        return
    # Auto-send is a purely LOCAL decision: the backend only certifies that the draft cleared
    # its non-negotiable safety floor (meets_safety_floor); the operator's mode, allowlist, and
    # quiet hours decide whether to actually send. In review mode everything is queued.
    if _local_auto_send_allowed(chat_id, reply):
        _send(chat_id, reply["draft"])
    else:
        _queue_for_review(chat_id, incoming, reply)
    # Commit dedup only after a successful queue/send. main() swallows exceptions to
    # stay alive, so marking earlier would drop a message that failed transiently.
    _mark_handled(dedup_key)


def main() -> int:
    if not os.environ.get("BEEPER_ACCESS_TOKEN"):
        print("BEEPER_ACCESS_TOKEN is required (run `beeper setup` first).", file=sys.stderr)
        return 2
    if not OMI_AUTH_TOKEN:
        print("OMI_AUTH_TOKEN is required.", file=sys.stderr)
        return 2
    base_url_error = _api_base_url_error()
    if base_url_error:
        print(base_url_error, file=sys.stderr)
        return 2

    print(f"[clone-bridge] watching Beeper; mode={CLONE_MODE}; allowlist={CLONE_ALLOWLIST or 'none'}")
    # `beeper watch --events` streams newline-delimited JSON events.
    proc = subprocess.Popen(["beeper", "watch", "--events"], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                _handle_event(event)
            except Exception as exc:  # noqa: BLE001 - keep the bridge alive on per-message errors
                print(f"[clone-bridge] error handling event: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
