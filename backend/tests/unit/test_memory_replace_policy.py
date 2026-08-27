"""Universal memory source-replacement and cascade-delete invariants."""

from __future__ import annotations

import ast
import importlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION_PATH = BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"
CONVERSATIONS_ROUTER_PATH = BACKEND_DIR / "routers" / "conversations.py"

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    CLIENT_BINDING_DATABASE_MODULES,
    WS_I_HEAVY_STUB_MODULE_NAMES,
    drop_client_binding_modules,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _memory_replace_import_isolation():
    saved = snapshot_sys_modules(
        [
            "database._client",
            "utils.conversations.process_conversation",
            *CLIENT_BINDING_DATABASE_MODULES,
            *WS_I_HEAVY_STUB_MODULE_NAMES,
        ]
    )
    install_database_client_stub()
    # Evict anything that already captured a live Firestore handle before stubbing.
    # Without this the stub install skips those names, _extract_memories_canonical
    # reaches the real database.notifications.get_user_time_zone, and the test spends
    # an hour in google.api_core retry backoff instead of 0.36s -- passing either way,
    # so only the clock shows it.
    drop_client_binding_modules()
    install_ws_i_heavy_import_stubs()
    yield
    restore_sys_modules(saved)


def _load_process_conversation():
    for name in list(sys.modules):
        if name == "utils.conversations.process_conversation" or name.startswith(
            "utils.conversations.process_conversation."
        ):
            del sys.modules[name]
    return importlib.import_module("utils.conversations.process_conversation")


def _function_body(source: str, fn_name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            start = node.lineno - 1
            end = node.end_lineno
            lines = source.splitlines()
            return "\n".join(lines[start:end])
    raise AssertionError(f"{fn_name} not found")


def test_conversation_extraction_has_no_historical_writer_or_selector():
    """Conversation finalization has one canonical source-replacement path."""
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    body = _function_body(source, "_extract_memories_inner")
    assert "_extract_memories_canonical" in body
    assert "memory_system" not in body
    assert "delete_memories_for_conversation" not in source
    assert "memories_db.save_memories" not in source


def test_canonical_extract_replaces_only_after_successful_parse():
    """Canonical re-extract must submit one replacement after extraction completes."""
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    body = _function_body(source, "_extract_memories_canonical")
    extract_idx = body.index("extract_canonical_l1_memory_candidates")
    replace_idx = body.index("replace_conversation_memories")
    assert extract_idx < replace_idx
    assert "retract_conversation_memories" not in body
    assert "memory_service.write" not in body


def test_cascade_delete_cleans_memories_before_conversation_doc():
    """Cascade delete must remove memories/action-items before the conversation document."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    fn_start = source.index("def delete_conversation(")
    fn_end = source.index("\n@router.", fn_start)
    body = source[fn_start:fn_end]
    conv_delete_idx = body.index("conversations_db.delete_conversation")
    cascade_idx = body.index("if cascade:")
    memories_idx = body.index("retract_conversation_memories")
    action_items_idx = body.index("delete_action_items_for_conversation")
    assert cascade_idx < memories_idx < conv_delete_idx
    assert cascade_idx < action_items_idx < conv_delete_idx


def test_universal_reextract_failure_preserves_existing_memories(monkeypatch):
    """Strict extraction failure must not submit a source replacement."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    # Intercept the MemoryService created inside _extract_memories_canonical
    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)

    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(side_effect=Exception("llm down")),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-canonical-preserve",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    with pytest.raises(Exception, match="llm down"):
        pc._extract_memories_inner("uid-canonical-preserve", conversation)

    mock_service.replace_conversation_memories.assert_not_called()


def test_universal_reextract_valid_empty_replaces_existing_source_state(monkeypatch):
    """A valid empty extraction is an authoritative source replacement."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(pc, "extract_canonical_l1_memory_candidates", MagicMock(return_value=[]))
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-canonical-empty",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    result = pc._extract_memories_inner("uid-canonical-empty", conversation)

    assert result.count == 0
    mock_service.replace_conversation_memories.assert_called_once_with(
        "uid-canonical-empty",
        conversation.id,
        [],
    )


def test_canonical_capture_preserves_prior_state_when_candidate_has_any_ungrounded_quote(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="The user was diagnosed with condition X.",
                    evidence_quotes=[
                        "We discussed ordinary weekend plans",
                        "I was diagnosed with condition X",
                    ],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-fabricated-quote",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="We discussed ordinary weekend plans and a grocery list.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-quote-grounding", conversation, db_client=MagicMock())

    # No replacement is submitted, so the source keeps the memories it already
    # has — and finalization still returns, so the caller's action items, audio
    # files and created webhook are not collateral of an extraction verdict.
    assert result.count == 0
    mock_service.replace_conversation_memories.assert_not_called()


def test_canonical_capture_preserves_prior_state_when_the_extractor_never_returns_a_batch(monkeypatch):
    """A provider failure is not a verdict on the source's existing memories.

    ``strict=True`` makes the extractor raise instead of returning an empty
    batch that would retract them. Skipping the replacement is that whole
    protection; propagating the raise additionally aborts the caller's
    finalization.
    """
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment
    from models.memory_contracts import WorkingObservationExtractionError

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(side_effect=WorkingObservationExtractionError("invoke")),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-extractor-unavailable",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="We discussed ordinary weekend plans and a grocery list.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-extractor-unavailable", conversation, db_client=MagicMock())

    assert result.count == 0
    mock_service.replace_conversation_memories.assert_not_called()


def test_canonical_capture_survives_an_external_text_extractor_failure(monkeypatch):
    """External-integration intake has the same extractor-failure boundary."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.memory_contracts import MemoryExtractionError

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_memories_from_text",
        MagicMock(side_effect=MemoryExtractionError("external_text_memory_extractor")),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-external-extractor-unavailable",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.external_integration,
        external_data={"text": "A long enough external note to reach the extractor.", "text_source": "other"},
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    result = pc._extract_memories_canonical("uid-external-extractor", conversation, db_client=MagicMock())

    assert result.count == 0
    mock_service.replace_conversation_memories.assert_not_called()


def test_canonical_capture_drops_only_the_ungrounded_candidate(monkeypatch):
    """One ungrounded candidate must not discard its grounded siblings."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="The user works at Acme.",
                    evidence_quotes=["I work at Acme"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                ),
                SimpleNamespace(
                    content="The user was diagnosed with condition X.",
                    evidence_quotes=["I was diagnosed with condition X"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                ),
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-partially-grounded",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I work at Acme and we talked about the grocery list.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-partial-grounding", conversation, db_client=MagicMock())

    assert result.count == 1
    replacement_payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert len(replacement_payloads) == 1
    assert replacement_payloads[0]["content"] == "The user works at Acme."


def test_canonical_capture_accepts_an_extractor_that_yields_no_candidates(monkeypatch):
    """An extractor that returns zero candidates is a quiet conversation, not a failed run.

    The all-ungrounded guard must key off candidates the loop actually saw. Keying
    off the returned container's truthiness misreads any truthy-but-empty iterable
    (a generator's stand-in, a test double) as "every candidate failed grounding"
    and aborts conversation finalization for a conversation with nothing to learn.
    """
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    # Truthy, but yields nothing — exactly what a bare MagicMock extractor does.
    monkeypatch.setattr(pc, "extract_canonical_l1_memory_candidates", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-no-candidates",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="We talked about the weather.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-no-candidates", conversation, db_client=MagicMock())

    assert result.count == 0
    replacement_payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert replacement_payloads == []


@pytest.mark.parametrize(
    "matched_segments",
    [
        [
            SimpleNamespace(is_user=True, person_id=None, speaker="SPEAKER_00", speaker_id=0),
            SimpleNamespace(is_user=False, person_id="sarah", speaker="SPEAKER_01", speaker_id=1),
        ],
        [
            SimpleNamespace(is_user=False, person_id="sarah", speaker="SPEAKER_01", speaker_id=1),
            SimpleNamespace(is_user=False, person_id=None, speaker="SPEAKER_01", speaker_id=1),
        ],
    ],
    ids=["user-and-identified", "identified-and-unidentified"],
)
def test_canonical_capture_requires_every_grounded_segment_to_resolve_to_one_subject(matched_segments):
    pc = _load_process_conversation()

    subject_id, attribution, subject_kind = pc._l1_subject_from_matched_segments(
        source_id="conv-mixed-subject",
        matched_segments=matched_segments,
    )

    assert subject_id is None
    assert attribution == pc.SubjectAttribution.unknown
    assert subject_kind == "unknown"


def test_canonical_capture_known_non_user_speaker_overrides_model_about_user(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="The speaker works at Acme.",
                    evidence_quotes=["I work at Acme!"],
                    speaker_label="SPEAKER_01",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-third-party-subject",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I work at Acme.",
                speaker="SPEAKER_01",
                is_user=False,
                person_id="other-person",
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-subject", conversation, db_client=MagicMock())

    assert result.count == 1
    replacement_payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert len(replacement_payloads) == 1
    payload = replacement_payloads[0]
    assert payload["subject_entity_id"] == "person:other-person"
    assert payload["subject_attribution"] == "third_party"


def test_canonical_capture_logs_text_free_regime_and_attribution_decision(monkeypatch, caplog):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    memory_text = "The other speaker works at a confidential company."
    quote_text = "I work at a confidential company"
    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content=memory_text,
                    evidence_quotes=[quote_text],
                    speaker_label="SPEAKER_01",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    conversation = Conversation(
        id="conv-desktop-decision-log",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.desktop,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I own this account",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=2.0,
            ),
            TranscriptSegment(
                text=f"{quote_text}.",
                speaker="SPEAKER_01",
                is_user=False,
                person_id="other-person",
                start=2.0,
                end=4.0,
            ),
        ],
    )

    with caplog.at_level(logging.INFO, logger=pc.__name__):
        result = pc._extract_memories_canonical(
            "uid-decision-log",
            conversation,
            db_client=MagicMock(),
        )

    assert result.count == 1
    messages = [
        record.getMessage() for record in caplog.records if "canonical_memory_decision_path.v1" in record.getMessage()
    ]
    assert len(messages) == 1
    event = json.loads(messages[0].split("canonical_memory_decision_path.v1 ", 1)[1])
    assert event == {
        "attribution_disagreed": True,
        "capture_regime": "desktop",
        "conversation_id": conversation.id,
        "distinct_speaker_ids": 2,
        "memory_id": mock_service.replace_conversation_memories.call_args.args[2][0]["id"],
        "model_about": "primary_user",
        # One speaker was flagged as the owner here. 0 (owner never identified) and
        # >1 (impossible -- an account has one owner) are the states that decide
        # whether anything from this conversation can ever be promoted, and neither
        # is derivable from distinct_speaker_ids.
        "owner_speaker_ids": 1,
        "stage": "capture",
        "subject_attribution": "third_party",
        "uid": "uid-decision-log",
    }
    assert memory_text not in messages[0]
    assert quote_text not in messages[0]


def test_canonical_capture_rejection_feedback_fetch_is_bounded_to_the_orchestration_boundary(monkeypatch):
    pc = _load_process_conversation()
    fallback = MagicMock()
    monkeypatch.setattr(pc, "record_fallback", fallback)
    monkeypatch.setattr(
        pc,
        "get_recent_rejected_memory_examples",
        lambda uid, *, db_client: (f"rejected-for-{uid}",),
    )

    assert pc._rejected_memory_examples_for_l1("uid-feedback", db_client=object()) == ("rejected-for-uid-feedback",)
    fallback.assert_not_called()

    monkeypatch.setattr(
        pc,
        "get_recent_rejected_memory_examples",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("query unavailable")),
    )

    assert pc._rejected_memory_examples_for_l1("uid-feedback", db_client=object()) == ()
    fallback.assert_called_once_with(
        component="other",
        from_mode="canonical_l1_rejection_feedback",
        to_mode="extraction_without_rejection_feedback",
        reason="other",
        outcome="degraded",
    )


def test_canonical_capture_maps_rendered_contact_name_back_to_person_id(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="Sarah prefers early flights.",
                    evidence_quotes=["I prefer early flights"],
                    speaker_label="Sarah",
                    speaker_scope="session-local",
                    about="Sarah",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-contact-name",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I prefer early flights.",
                speaker="SPEAKER_01",
                is_user=False,
                person_id="contact-sarah",
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical(
        "uid-contact-name",
        conversation,
        db_client=MagicMock(),
    )

    assert result.count == 1
    payload = mock_service.replace_conversation_memories.call_args.args[2][0]
    assert payload["subject_entity_id"] == "person:contact-sarah"
    assert payload["subject_attribution"] == "third_party"
    assert payload["subject_kind"] == "person"
    assert payload["evidence"][0]["quote_refs"][0]["speaker_label"] == "SPEAKER_01"


def test_canonical_capture_quote_speaker_overrides_hallucinated_user_label(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="The speaker works at Acme.",
                    evidence_quotes=["I work at Acme!"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-spoofed-speaker",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I work at Acme.",
                speaker="SPEAKER_01",
                is_user=False,
                person_id="other-person",
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical("uid-spoofed-speaker", conversation, db_client=MagicMock())

    assert result.count == 1
    replacement_payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert len(replacement_payloads) == 1
    payload = replacement_payloads[0]
    assert payload["subject_entity_id"] == "person:other-person"
    assert payload["subject_attribution"] == "third_party"


def test_canonical_capture_source_scopes_unidentified_subject_from_matched_speaker(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="The unidentified speaker works at Acme.",
                    evidence_quotes=["I work at Acme!"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the user",
                    risk_flags=[],
                    archive_class="general",
                )
            ]
        ),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-source-speaker-subject",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                text="I work at Acme.",
                speaker="SPEAKER_01",
                is_user=False,
                start=0.0,
                end=4.0,
            )
        ],
    )

    result = pc._extract_memories_canonical(
        "uid-source-speaker-subject",
        conversation,
        db_client=MagicMock(),
    )

    assert result.count == 1
    payload = mock_service.replace_conversation_memories.call_args.args[2][0]
    expected_subject = pc._source_scoped_l1_subject_id(
        source_id=conversation.id,
        kind="speaker",
        label="SPEAKER_01",
    )
    model_authored_subject = pc._source_scoped_l1_subject_id(
        source_id=conversation.id,
        kind="speaker",
        label="SPEAKER_00",
    )
    assert payload["subject_entity_id"] == expected_subject
    assert payload["subject_entity_id"] != model_authored_subject
    assert payload["subject_kind"] == "speaker"
    assert payload["evidence"][0]["quote_refs"][0]["speaker_label"] == "SPEAKER_01"


def test_canonical_dense_capture_is_bounded_before_atomic_replacement(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment
    from utils.llm.working_observations import MAX_WORKING_OBSERVATION_ITEMS

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    candidates = [
        SimpleNamespace(
            content=f"Durable observation {index}",
            evidence_quotes=[f"source quote number {index}"],
            speaker_label="SPEAKER_00",
            speaker_scope="session-local",
            about="the user",
            risk_flags=[],
            archive_class="general",
        )
        for index in range(60)
    ]
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(return_value=candidates),
    )
    conversation = Conversation(
        id="conv-dense-capture",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                id=f"segment-{index}",
                text=f"source quote number {index}",
                speaker="SPEAKER_00",
                is_user=True,
                start=float(index),
                end=float(index + 1),
            )
            for index in range(60)
        ],
        is_locked=True,
    )

    result = pc._extract_memories_canonical(
        "uid-dense-capture",
        conversation,
        db_client=MagicMock(),
    )

    payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert result.count == MAX_WORKING_OBSERVATION_ITEMS
    assert len(payloads) == MAX_WORKING_OBSERVATION_ITEMS
    assert [payload["content"] for payload in payloads] == [
        f"Durable observation {index}" for index in range(MAX_WORKING_OBSERVATION_ITEMS)
    ]


def test_canonical_capture_deduplicates_per_subject_and_assigns_subject_scoped_ids(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content="Prefers tea",
                    evidence_quotes=["I really prefer tea"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the speaker",
                    risk_flags=[],
                    archive_class="general",
                ),
                SimpleNamespace(
                    content="  PREFERS   TEA ",
                    evidence_quotes=["I really prefer tea"],
                    speaker_label="SPEAKER_00",
                    speaker_scope="session-local",
                    about="the speaker",
                    risk_flags=[],
                    archive_class="general",
                ),
                SimpleNamespace(
                    content="Prefers tea",
                    evidence_quotes=["Tea is my preference"],
                    speaker_label="SPEAKER_01",
                    speaker_scope="session-local",
                    about="the speaker",
                    risk_flags=[],
                    archive_class="general",
                ),
            ]
        ),
    )
    conversation = Conversation(
        id="conv-subject-aware-dedup",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[
            TranscriptSegment(
                id="segment-alice",
                text="I really prefer tea.",
                speaker="SPEAKER_00",
                is_user=False,
                person_id="alice",
                start=0.0,
                end=1.0,
            ),
            TranscriptSegment(
                id="segment-bob",
                text="Tea is my preference.",
                speaker="SPEAKER_01",
                is_user=False,
                person_id="bob",
                start=1.0,
                end=2.0,
            ),
        ],
        is_locked=True,
    )

    result = pc._extract_memories_canonical(
        "uid-subject-aware-dedup",
        conversation,
        db_client=MagicMock(),
    )

    payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert result.count == 2
    assert [payload["subject_entity_id"] for payload in payloads] == ["person:alice", "person:bob"]
    assert len({payload["id"] for payload in payloads}) == 2
