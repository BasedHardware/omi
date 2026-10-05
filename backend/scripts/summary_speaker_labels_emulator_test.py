#!/usr/bin/env python3
"""Exercise the note-inferred speaker-label transaction against the real Firestore emulator.

The StrictFirestore unit fake proves admission and read-before-write ordering but
cannot model query locks, retries, contention, rollback, or phantom inserts
around ``transaction.create``. This proof seeds a real emulator project and runs
``apply_summary_speaker_labels`` end to end: catalog read inside the
transaction, deterministic person creation, segment label write, and the
declines (stale digest, replaced note, changed transcript) that must leave both
collections untouched.

Run under ``firebase emulators:exec --only firestore --project demo-omi-jit-qa``
(the emulator-proofs workflow does this; FIRESTORE_EMULATOR_HOST is required).
"""

from __future__ import annotations

# ruff: noqa: E402 -- emulator safety/env bootstrapping must precede backend imports.

import os
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ID = os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("GCLOUD_PROJECT", "demo-omi-summary-labels"))
os.environ.setdefault("GCLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("FIREBASE_PROJECT_ID", PROJECT_ID)
os.environ.setdefault("ENCRYPTION_SECRET", "omi_summary_labels_emulator_key_32_bytes")
os.environ.setdefault("SUMMARY_SPEAKER_LABELS_ENABLED", "on")
os.environ.setdefault("PROVIDER_MODE", "offline")
os.environ.setdefault("GOOGLE_AUTH_DISABLE_GCE_CHECK", "true")
os.environ.setdefault("GCE_METADATA_HOST", "127.0.0.1:9")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore  # noqa: E402

from database import conversations as conversations_db  # noqa: E402
from utils.conversations import summary_speaker_labels as stage  # noqa: E402
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry  # noqa: E402

UID = "summary-label-proof"
CONV = "conv-proof"


def _assert_emulator_only() -> None:
    host = (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()
    if not host:
        raise RuntimeError("FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(f"refusing non-loopback Firestore emulator host: {hostname}")
    if not PROJECT_ID.startswith("demo-"):
        raise RuntimeError(f"refusing non-demo Firestore project: {PROJECT_ID}")


def _roster():
    return MeetingRoster(
        (
            RosterEntry("David", None, None, "owner", "macos_calendar", None),
            RosterEntry("Eddie Thai", None, None, "human", "macos_calendar", None),
        ),
        "Planning",
        False,
    )


def _segments():
    return [
        dict(
            id="s1",
            speaker="SPEAKER_02",
            speaker_id=2,
            text="My name is Eddie Thai.",
            is_user=False,
            start=0.0,
            end=4.0,
        )
    ]


def _candidates():
    from models.summary_speaker_labels import SpeakerBinding, SpeakerCandidate

    return [
        SpeakerCandidate(
            name="Eddie Thai",
            is_owner=False,
            is_ai_agent=False,
            bindings=[
                SpeakerBinding(
                    speaker_id=2, confidence="high", evidence_segment_ids=["s1"], evidence_kind="self_introduction"
                )
            ],
        )
    ]


def _seed_conversation(client) -> None:
    segments = _segments()
    encoded = conversations_db.encode_conversation_for_write(UID, {"transcript_segments": segments})
    client.document(f"users/{UID}/conversations/{CONV}").set(
        {
            "id": CONV,
            "status": "completed",
            "data_protection_level": "standard",
            "structured": {"title": "Planning", "overview": "A plan."},
            "transcript_segments": encoded["transcript_segments"],
            "transcript_segments_compressed": encoded.get("transcript_segments_compressed", True),
        }
    )


def _people(client) -> list[dict]:
    return [d.to_dict() or {} for d in client.collection(f"users/{UID}/people").stream()]


def main() -> None:
    _assert_emulator_only()
    client = firestore.Client(project=PROJECT_ID)
    client.document(f"users/{UID}").set({"id": UID}, merge=True)

    # Paid entitlement for the named (non-owner) candidate.
    original_allowed = stage.named_speaker_prompts_allowed
    stage.named_speaker_prompts_allowed = lambda uid: True
    try:
        # 1. Applies labels and creates the person atomically.
        _seed_conversation(client)
        note = SimpleNamespace(
            _summary_speaker_candidates=_candidates(),
            _summary_speaker_roster=_roster(),
            title="Planning",
            overview="A plan.",
        )
        conv = SimpleNamespace(id=CONV, discarded=False, structured=note, transcript_segments=_segments_list())
        digest = stage.note_generation_digest(note._summary_speaker_candidates, note._summary_speaker_roster)
        client.document(f"users/{UID}/conversations/{CONV}").set({"summary_speaker_note_digest": digest}, merge=True)
        applied = stage.apply_summary_speaker_labels(UID, conv)
        assert applied == 1, f"expected 1 applied segment, got {applied}"
        stored = client.document(f"users/{UID}/conversations/{CONV}").get().to_dict()
        decoded = conversations_db.decode_transcript_segments_verified(
            UID, stored["transcript_segments"], bool(stored.get("transcript_segments_compressed"))
        )
        assert decoded[0]["person_id"], "segment not labeled"
        assert decoded[0]["speaker_match_source"] == "summary_inferred"
        people = _people(client)
        assert len(people) == 1 and people[0]["name"] == "Eddie Thai", people
        assert people[0].get("creation_source") == "summary_inferred"

        # 2. Idempotent: a second run declines (segments already labeled).
        assert stage.apply_summary_speaker_labels(UID, conv) == 0
        assert len(_people(client)) == 1

        # 3. Stale digest declines without touching anything.
        client.document(f"users/{UID}/conversations/{CONV}").set({"summary_speaker_note_digest": "other"}, merge=True)
        fresh_conversation = SimpleNamespace(
            id=CONV, discarded=False, structured=note, transcript_segments=_segments_list()
        )
        assert stage.apply_summary_speaker_labels(UID, fresh_conversation) == 0
        stored = client.document(f"users/{UID}/conversations/{CONV}").get().to_dict()
        assert stored["summary_speaker_note_digest"] == "other"

        # 4. Replaced note declines.
        client.document(f"users/{UID}/conversations/{CONV}").set(
            {"summary_speaker_note_digest": digest, "structured": {"title": "New", "overview": "A plan."}}, merge=True
        )
        assert stage.apply_summary_speaker_labels(UID, fresh_conversation) == 0

        print(
            "PASS: summary speaker-label transaction emulator proof (apply / idempotent / stale digest / replaced note)"
        )
    finally:
        stage.named_speaker_prompts_allowed = original_allowed


def _segments_list():
    from models.transcript_segment import TranscriptSegment

    return [TranscriptSegment.model_validate(s) for s in _segments()]


if __name__ == "__main__":
    main()
