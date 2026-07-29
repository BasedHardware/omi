"""Memory replace policy — legacy re-extract and cascade delete invariants."""

from __future__ import annotations

import ast
import importlib
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
    WS_I_HEAVY_STUB_MODULE_NAMES,
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
            *WS_I_HEAVY_STUB_MODULE_NAMES,
        ]
    )
    install_database_client_stub()
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


def test_legacy_extract_deletes_only_after_successful_parse():
    """Legacy re-extract must not delete conversation memories before extraction completes."""
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    body = _function_body(source, "_extract_memories_legacy")
    delete_idx = body.index("delete_memories_for_conversation")
    extract_idx = body.index("new_memories_extractor")
    save_idx = body.index("save_memories")
    assert (
        extract_idx < delete_idx < save_idx
    ), "legacy path must extract, then delete old conversation memories, then save new ones"


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
    memories_idx = body.index("delete_memories_for_conversation")
    action_items_idx = body.index("delete_action_items_for_conversation")
    assert cascade_idx < memories_idx < conv_delete_idx
    assert cascade_idx < action_items_idx < conv_delete_idx


@pytest.mark.parametrize("extractor_side_effect", [Exception("llm down"), []])
def test_legacy_reextract_failure_preserves_existing_memories(extractor_side_effect, monkeypatch):
    """If extraction fails or yields nothing, prior conversation memories must remain."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock(return_value={"vector_delete_ids": ["old-mem-1"]})
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()

    monkeypatch.setattr(
        pc,
        "new_memories_extractor",
        MagicMock(
            side_effect=extractor_side_effect if isinstance(extractor_side_effect, Exception) else lambda *a, **k: []
        ),
    )
    monkeypatch.setattr(
        pc,
        "memory_system_request_scope",
        lambda uid: MagicMock(__enter__=lambda s: pc.MemorySystem.LEGACY, __exit__=lambda *a: None),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(pc.notification_db, "get_user_time_zone", lambda uid: "UTC")

    conversation = Conversation(
        id="conv-preserve",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    if isinstance(extractor_side_effect, Exception):
        with pytest.raises(Exception, match="llm down"):
            pc._extract_memories_inner("uid-preserve", conversation)
    else:
        pc._extract_memories_inner("uid-preserve", conversation)

    legacy_delete.assert_not_called()
    legacy_save.assert_not_called()


def test_canonical_reextract_failure_preserves_existing_memories(monkeypatch):
    """Canonical path: strict extraction failure must not submit a replacement."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    # Intercept the MemoryService created inside _extract_memories_canonical
    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)

    monkeypatch.setattr(
        pc,
        "extract_canonical_l1_memory_candidates",
        MagicMock(side_effect=Exception("llm down")),
    )
    monkeypatch.setattr(
        pc,
        "memory_system_request_scope",
        lambda uid: MagicMock(__enter__=lambda s: pc.MemorySystem.CANONICAL, __exit__=lambda *a: None),
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


def test_canonical_reextract_valid_empty_replaces_existing_source_state(monkeypatch):
    """A valid empty canonical extraction is an authoritative source replacement."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
    monkeypatch.setattr(pc, "extract_canonical_l1_memory_candidates", MagicMock(return_value=[]))
    monkeypatch.setattr(
        pc,
        "memory_system_request_scope",
        lambda uid: MagicMock(__enter__=lambda s: pc.MemorySystem.CANONICAL, __exit__=lambda *a: None),
    )
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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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

    with pytest.raises(
        ValueError,
        match="evidence without a unique source binding",
    ):
        pc._extract_memories_canonical("uid-quote-grounding", conversation)

    mock_service.replace_conversation_memories.assert_not_called()


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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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

    result = pc._extract_memories_canonical("uid-subject", conversation)

    assert result.count == 1
    replacement_payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert len(replacement_payloads) == 1
    payload = replacement_payloads[0]
    assert payload["subject_entity_id"] == "person:other-person"
    assert payload["subject_attribution"] == "third_party"


def test_canonical_capture_maps_rendered_contact_name_back_to_person_id(monkeypatch):
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment

    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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

    result = pc._extract_memories_canonical("uid-spoofed-speaker", conversation)

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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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
    monkeypatch.setattr(pc, "MemoryService", lambda: mock_service)
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
    )

    payloads = mock_service.replace_conversation_memories.call_args.args[2]
    assert result.count == 2
    assert [payload["subject_entity_id"] for payload in payloads] == ["person:alice", "person:bob"]
    assert len({payload["id"] for payload in payloads}) == 2
