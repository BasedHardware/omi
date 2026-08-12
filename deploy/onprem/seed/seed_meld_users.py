#!/usr/bin/env python3
"""Seed Omi users with realistic multi-speaker conversations from MELD (Friends), via the backend HTTP
API — exactly as a real app user would (OIDC-authenticated, on-device-transcription path). No raw DB
writes: every conversation goes through POST /v1/conversations/from-segments, so the full product
pipeline runs (memories + action_items + summary + Qdrant vectors).

WHY MELD: it is multi-party dialogue with NAMED, recurring speakers (Ross, Rachel, Monica, ...), which
maps 1:1 onto Omi's identified-person model (transcript segment person_id -> Person(name)).

MELD IS NOT COMMITTED (TV-derived, research-use only). Download train_sent_emo.csv yourself, e.g.:

  # Option A — HuggingFace datasets (recommended)
  pip install datasets pandas
  python -c "from datasets import load_dataset; d=load_dataset('declare-lab/MELD','MELD'); \
             d['train'].to_pandas().to_csv('train_sent_emo.csv', index=False)"

  # Option B — raw CSV from the project repo
  curl -L -o train_sent_emo.csv \
    https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/train_sent_emo.csv

Then run (dev stack up with OIDC auth + chat + qdrant + embeddings — see SELFHOST_NOTES):
  deploy/onprem/seed/seed_meld_users.py --meld-csv train_sent_emo.csv --per-user 20

Prereqs (dev stack, --profile auth,chat + qdrant, AUTH_BACKEND=oidc, LOCAL_DEVELOPMENT=false):
  - Keycloak (realm 'omi', public direct-access client 'omi-test') reachable at --kc-url.
  - Backend reachable at --api-url, validating the same issuer's JWKS.
  - Operator LLM (chat, e.g. qwen2.5:14b via the gateway) + a 1024-dim embeddings model
    (e.g. bge-m3) so processing can generate memories and Qdrant vectors.

Everything here is idempotent: users, People (by name), and re-running is safe (conversations are
appended; use a fresh Qdrant/emulator to start clean).
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# --- The 5 seeded users. Each embodies a primary Friends character: that character's turns are the
# user's own (is_user=True); every other named speaker in the dialogue becomes one of the user's
# identified People (person_id). Usernames/emails are arbitrary app identities. -----------------
USERS = [
    {"username": "ross", "character": "Ross", "email": "ross@omi.test", "first": "Ross", "last": "Geller"},
    {"username": "rachel", "character": "Rachel", "email": "rachel@omi.test", "first": "Rachel", "last": "Green"},
    {"username": "monica", "character": "Monica", "email": "monica@omi.test", "first": "Monica", "last": "Geller"},
    {"username": "chandler", "character": "Chandler", "email": "chandler@omi.test", "first": "Chandler", "last": "Bing"},
    {"username": "joey", "character": "Joey", "email": "joey@omi.test", "first": "Joey", "last": "Tribbiani"},
]
DEFAULT_PASSWORD = "seed-Passw0rd!"

# Fact-rich "profile" conversations per user. MELD (Friends banter) yields conversations, action items,
# identified people and retrieval vectors — but almost no MEMORIES, because the memory extractor is a
# strict curator of durable personal facts about the user, which scripted banter lacks. These seed a
# realistic "getting to know you" first session per user (explicit facts about their life) so the
# pipeline produces real memories. Each entry: (is_user, text). The user states facts; an interlocutor
# prompts. Canonical Friends facts keep them consistent with the MELD people.
PROFILE_CONVERSATIONS = {
    "Ross": [
        (True, "I'm Ross. I work as a paleontologist at the Museum of Natural History — I've loved dinosaurs since I was a kid."),
        (False, "That's amazing. How's life outside work?"),
        (True, "I'm divorced and I have a son, Ben. My sister Monica lives here in New York and we're really close."),
        (True, "I'm lactose intolerant, so I avoid dairy. And I've been trying to learn the keyboard lately."),
        (False, "Any advice you live by?"),
        (True, "My therapist always says consistency matters more than perfection. I try to remember that."),
    ],
    "Rachel": [
        (True, "I'm Rachel. I just started working in fashion — I'm an assistant buyer at Bloomingdale's and I want to build a real career."),
        (False, "Congrats! What's your background?"),
        (True, "I grew up wealthy in Long Island but I'm supporting myself now. My best friend Monica lets me stay with her."),
        (True, "I'm scared of bugs and I love shopping. I recently stopped a wedding I didn't want."),
        (False, "What matters to you now?"),
        (True, "Independence. I learned you have to bet on yourself even when it's terrifying."),
    ],
    "Monica": [
        (True, "I'm Monica. I'm a head chef — cooking is my whole life and I'm extremely competitive about it."),
        (False, "Nice! What are you like at home?"),
        (True, "I'm a total neat freak and I love hosting. My brother Ross and my friends are always at my apartment."),
        (True, "I used to be overweight as a teenager, and I'm allergic to nothing but I hate mess."),
        (False, "A lesson you'd share?"),
        (True, "My grandmother taught me that feeding people is how you show love. I really believe that."),
    ],
    "Chandler": [
        (True, "I'm Chandler. I work in statistical analysis and data reconfiguration — honestly people never remember my job title."),
        (False, "Ha! What about your personal life?"),
        (True, "I use humor to deal with everything. My parents divorced when I was young, which is why I make jokes."),
        (True, "My best friend and roommate is Joey. I quit smoking recently and I hate Thanksgiving for personal reasons."),
        (False, "Any wisdom?"),
        (True, "A mentor told me that sarcasm is easy but vulnerability is what actually connects people."),
    ],
    "Joey": [
        (True, "I'm Joey. I'm a struggling actor — I was on a soap opera called Days of Our Lives and I love the craft."),
        (False, "Cool! Tell me about you."),
        (True, "I'm from a big Italian family in Queens with seven sisters. Food and friends are everything to me."),
        (True, "I never share food, and my roommate Chandler is my best friend. I'm terrible with money but great with people."),
        (False, "Something you believe?"),
        (True, "My father taught me that loyalty to your friends is the most important thing in the world."),
    ],
}

# MELD occasionally labels a line with a non-name token; skip those as identified people but keep the
# turn (rendered as "Speaker N").
_NON_PERSON_SPEAKERS = {"", "all", "everyone", "the", "man", "woman", "guys", "both"}


def _ctx_no_verify() -> ssl.SSLContext:
    """Dev stacks front Keycloak/the API with a self-signed cert; skip verification for seeding."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http(method: str, url: str, *, headers=None, data=None, form=None, expect=(200, 201, 204, 409)):
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers = {**(headers or {}), "Content-Type": "application/x-www-form-urlencoded"}
    elif data is not None:
        body = json.dumps(data).encode()
        headers = {**(headers or {}), "Content-Type": "application/json"}
    else:
        body = None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=_ctx_no_verify(), timeout=120) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if e.code in expect:
            return e.code, raw
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:400]}") from None


# --- Keycloak -----------------------------------------------------------------------------------
def kc_admin_token(kc_url: str, admin_user: str, admin_pass: str) -> str:
    _, tok = _http(
        "POST",
        f"{kc_url}/realms/master/protocol/openid-connect/token",
        form={"grant_type": "password", "client_id": "admin-cli", "username": admin_user, "password": admin_pass},
        expect=(200,),
    )
    return tok["access_token"]


def kc_ensure_user(kc_url: str, realm: str, admin_tok: str, u: dict, password: str) -> None:
    """Create the realm user with a permanent password, idempotently (409 = already exists)."""
    hdr = {"Authorization": f"Bearer {admin_tok}"}
    payload = {
        "username": u["username"],
        "email": u["email"],
        "firstName": u["first"],
        "lastName": u["last"],
        "emailVerified": True,
        "enabled": True,
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    status, _ = _http("POST", f"{kc_url}/admin/realms/{realm}/users", headers=hdr, data=payload)
    if status == 409:
        # Already there — reset the password so the run is self-contained.
        _, users = _http(
            "GET",
            f"{kc_url}/admin/realms/{realm}/users?username={urllib.parse.quote(u['username'])}&exact=true",
            headers=hdr,
            expect=(200,),
        )
        uid = users[0]["id"]
        _http(
            "PUT",
            f"{kc_url}/admin/realms/{realm}/users/{uid}/reset-password",
            headers=hdr,
            data={"type": "password", "value": password, "temporary": False},
            expect=(204,),
        )


def kc_user_token(kc_url: str, realm: str, client_id: str, username: str, password: str) -> str:
    _, tok = _http(
        "POST",
        f"{kc_url}/realms/{realm}/protocol/openid-connect/token",
        form={"grant_type": "password", "client_id": client_id, "username": username, "password": password,
              "scope": "openid email profile"},
        expect=(200,),
    )
    return tok["access_token"]


# --- Backend API --------------------------------------------------------------------------------
def api_get_or_create_person(api_url: str, token: str, name: str) -> str:
    _, person = _http(
        "POST", f"{api_url}/v1/users/people", headers={"Authorization": f"Bearer {token}"},
        data={"name": name[:40]}, expect=(200, 201),
    )
    return person["id"]


def api_create_conversation(api_url: str, token: str, segments: list, started_at: datetime,
                            source="omi", language="en", *, retries=3) -> dict:
    # source=omi (mobile-like) processes EAGERLY: full LLM enrichment (overview, action_items,
    # memories) + Qdrant vectors at creation. source=desktop would defer enrichment to first open
    # (a Free-tier desktop cost policy, should_defer_desktop_processing) — not what a seed wants.
    # A local model (e.g. qwen2.5:14b) occasionally emits unparseable structured output -> the
    # endpoint 500s (OutputParserException). Retry: the model resamples and usually parses next time.
    import time

    payload = {"transcript_segments": segments, "source": source,
               "started_at": started_at.isoformat(), "language": language}
    last = None
    for attempt in range(1, retries + 1):
        try:
            _, conv = _http("POST", f"{api_url}/v1/conversations/from-segments",
                            headers={"Authorization": f"Bearer {token}"}, data=payload, expect=(200, 201))
            return conv
        except RuntimeError as e:
            last = e
            if "-> 500" not in str(e) or attempt == retries:
                raise
            time.sleep(2.0 * attempt)
    raise last  # unreachable


def api_wait_enriched(api_url: str, token: str, conv_id: str, *, attempts=30, delay=2.0) -> dict:
    """Poll until the conversation's async enrichment (LLM structured + memories + vectors) finishes.

    Also paces the seed to one in-flight conversation at a time, which keeps concurrent embed+LLM
    calls off a single GPU (avoids cudaMalloc OOM). Returns the last state seen."""
    import time

    conv = {}
    for _ in range(attempts):
        _, conv = _http("GET", f"{api_url}/v1/conversations/{conv_id}",
                        headers={"Authorization": f"Bearer {token}"}, expect=(200,))
        st = (conv.get("structured") or {}) if isinstance(conv, dict) else {}
        if isinstance(conv, dict) and conv.get("status") == "completed" and not conv.get("deferred") and st.get("overview"):
            return conv
        time.sleep(delay)
    return conv


# --- MELD -> Omi mapping ------------------------------------------------------------------------
def load_meld_dialogues(csv_path: str):
    """Return {dialogue_id: [utterance_row, ...]} ordered by Utterance_ID."""
    dialogues = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            dialogues[row["Dialogue_ID"]].append(row)
    for did in dialogues:
        dialogues[did].sort(key=lambda r: int(r["Utterance_ID"]))
    return dialogues


def _norm_speaker(name: str) -> str:
    return (name or "").strip()


def build_segments(rows: list, primary_character: str, person_ids: dict) -> list:
    """Map MELD utterances to Omi transcript segments. The primary character -> is_user; every other
    named speaker -> its Person(person_id). Timing is synthesized as a monotonic 3s/utterance clock
    (MELD's StartTime/EndTime are HH:MM:SS,mmm strings relative to each clip, not usable directly)."""
    segments, t = [], 0.0
    speaker_slots: dict[str, int] = {}
    for r in rows:
        spk = _norm_speaker(r["Speaker"])
        text = (r.get("Utterance") or "").strip()
        if not text:
            continue
        is_user = spk.lower() == primary_character.lower()
        # Stable SPEAKER_NN per distinct speaker within the dialogue (drives diarization speaker_id).
        slot = speaker_slots.setdefault(spk, len(speaker_slots))
        seg = {
            "text": text,
            "speaker": f"SPEAKER_{slot:02d}",
            "is_user": is_user,
            "start": round(t, 1),
            "end": round(t + 2.5, 1),
        }
        if not is_user and spk.lower() not in _NON_PERSON_SPEAKERS:
            seg["person_id"] = person_ids[spk]
        segments.append(seg)
        t += 3.0
    return segments


def build_profile_segments(turns: list) -> list:
    """Segments for a fact-rich profile conversation: user turns -> is_user, interlocutor -> plain."""
    segments, t = [], 0.0
    for is_user, text in turns:
        segments.append({
            "text": text,
            "speaker": "SPEAKER_00" if is_user else "SPEAKER_01",
            "is_user": is_user,
            "start": round(t, 1),
            "end": round(t + 3.0, 1),
        })
        t += 3.5
    return segments


def select_dialogues_for(dialogues: dict, character: str, per_user: int) -> list:
    """Dialogues where the character speaks the most turns (their own conversations), richest first."""
    scored = []
    for did, rows in dialogues.items():
        own = sum(1 for r in rows if _norm_speaker(r["Speaker"]).lower() == character.lower())
        distinct = len({_norm_speaker(r["Speaker"]) for r in rows})
        if own >= 2 and distinct >= 2:  # needs the user + at least one identified other
            scored.append((own, len(rows), did))
    scored.sort(reverse=True)
    return [did for _, _, did in scored[:per_user]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--meld-csv", required=True, help="Path to MELD train_sent_emo.csv (not committed)")
    ap.add_argument("--api-url", default="http://localhost:8000", help="Backend base URL")
    ap.add_argument("--kc-url", default="https://localhost:8443", help="Keycloak base URL (kc-proxy)")
    ap.add_argument("--realm", default="omi")
    ap.add_argument("--client-id", default="omi-test", help="Public direct-access-grants client")
    ap.add_argument("--kc-admin-user", default="admin")
    ap.add_argument("--kc-admin-pass", default="admin")
    ap.add_argument("--password", default=DEFAULT_PASSWORD, help="Password set for every seeded user")
    ap.add_argument("--per-user", type=int, default=20, help="Conversations per user (grow later)")
    ap.add_argument("--source", default="omi", help="Conversation source; 'omi' processes eagerly "
                    "(memories/vectors at creation). 'desktop' defers to first open — avoid for seeding.")
    ap.add_argument("--dry-run", action="store_true", help="Map and report, but make no API calls")
    args = ap.parse_args()

    print(f"== loading MELD from {args.meld_csv} ==")
    dialogues = load_meld_dialogues(args.meld_csv)
    print(f"   {len(dialogues)} dialogues loaded")

    if not args.dry_run:
        admin_tok = kc_admin_token(args.kc_url, args.kc_admin_user, args.kc_admin_pass)
        print("== provisioning Keycloak users ==")
        for u in USERS:
            kc_ensure_user(args.kc_url, args.realm, admin_tok, u, args.password)
            print(f"   user {u['username']} ready")

    grand_total = 0
    for u in USERS:
        character = u["character"]
        picks = select_dialogues_for(dialogues, character, args.per_user)
        print(f"\n== {u['username']} ({character}): {len(picks)} conversations ==")
        if args.dry_run:
            others = sorted({_norm_speaker(r["Speaker"]) for did in picks for r in dialogues[did]
                             if _norm_speaker(r["Speaker"]).lower() != character.lower()})
            print(f"   identified people (sample): {others[:12]}{' …' if len(others) > 12 else ''}")
            grand_total += len(picks)
            continue

        token = kc_user_token(args.kc_url, args.realm, args.client_id, u["username"], args.password)
        # Pre-create People (by name) for every non-primary speaker across this user's dialogues.
        names = sorted({_norm_speaker(r["Speaker"]) for did in picks for r in dialogues[did]
                        if _norm_speaker(r["Speaker"]).lower() != character.lower()
                        and _norm_speaker(r["Speaker"]).lower() not in _NON_PERSON_SPEAKERS
                        and 2 <= len(_norm_speaker(r["Speaker"])) <= 40})
        person_ids = {n: api_get_or_create_person(args.api_url, token, n) for n in names}
        print(f"   {len(person_ids)} identified people created")

        # Fact-rich profile conversation first -> real memories (MELD banter alone yields none).
        profile = PROFILE_CONVERSATIONS.get(character)
        if profile:
            conv = api_create_conversation(args.api_url, token, build_profile_segments(profile),
                                           started_at=datetime.now(timezone.utc) - timedelta(days=args.per_user + 1),
                                           source=args.source)
            enriched = api_wait_enriched(args.api_url, token, conv["id"])
            st = enriched.get("structured") or {}
            print(f"   [profile] {enriched.get('status')}: {(st.get('title') or conv['id'])[:44]!r}")

        base = datetime.now(timezone.utc) - timedelta(days=len(picks))
        for i, did in enumerate(picks):
            segments = build_segments(dialogues[did], character, person_ids)
            if len(segments) < 2:
                continue
            conv = api_create_conversation(args.api_url, token, segments,
                                           started_at=base + timedelta(days=i), source=args.source)
            enriched = api_wait_enriched(args.api_url, token, conv["id"])
            st = enriched.get("structured") or {}
            print(f"   [{i+1}/{len(picks)}] {enriched.get('status')}: "
                  f"{(st.get('title') or conv['id'])[:48]!r} "
                  f"(overview={len(st.get('overview') or '')} actions={len(st.get('action_items') or [])})")
            grand_total += 1

    print(f"\n== done: {grand_total} conversations {'(dry-run)' if args.dry_run else 'seeded via API'} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
