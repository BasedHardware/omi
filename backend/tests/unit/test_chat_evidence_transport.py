from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.chat import ChatEvidenceEnvelope, Message


def _message(**overrides):
    values = {
        "id": "answer-1",
        "text": "The release review happened yesterday.",
        "created_at": datetime.now(timezone.utc),
        "sender": "ai",
        "type": "text",
    }
    values.update(overrides)
    return Message(**values)


def test_message_round_trips_bounded_versioned_evidence() -> None:
    message = _message(
        evidence={
            "schema_version": 1,
            "references": [
                {
                    "id": "conversation:conv-1:segment:s1",
                    "kind": "conversation_segment",
                    "state": "available",
                    "conversation_id": "conv-1",
                    "segment_id": "s1",
                    "start_ms": 1000,
                    "end_ms": 2000,
                }
            ],
        }
    )

    assert message.model_dump(mode="json")["evidence"] == {
        "schema_version": 1,
        "request_id": None,
        "references": [
            {
                "id": "conversation:conv-1:segment:s1",
                "kind": "conversation_segment",
                "state": "available",
                "title": None,
                "summary": None,
                "conversation_id": "conv-1",
                "segment_id": "s1",
                "frame_id": None,
                "request_id": None,
                "start_ms": 1000,
                "end_ms": 2000,
                "captured_at_ms": None,
                "error_code": None,
                "error_message": None,
                "metadata": {},
            }
        ],
    }


@pytest.mark.parametrize(
    "reference",
    [
        {"id": " ", "kind": "conversation_summary", "state": "available", "conversation_id": "conv-1"},
        {"id": "ref-1", "kind": "conversation_segment", "state": "available", "conversation_id": "conv-1"},
        {"id": "ref-1", "kind": "keyframe", "state": "available"},
        {
            "id": "ref-1",
            "kind": "conversation_segment",
            "state": "available",
            "conversation_id": "conv-1",
            "segment_id": "s1",
            "start_ms": 2000,
            "end_ms": 1000,
        },
    ],
)
def test_evidence_identity_fails_closed(reference) -> None:
    with pytest.raises(ValidationError):
        ChatEvidenceEnvelope(references=[reference])


def test_evidence_envelope_rejects_duplicate_and_oversized_lists() -> None:
    reference = {
        "id": "conversation:conv-1:summary",
        "kind": "conversation_summary",
        "state": "available",
        "conversation_id": "conv-1",
    }
    with pytest.raises(ValidationError):
        ChatEvidenceEnvelope(references=[reference, reference])

    with pytest.raises(ValidationError):
        ChatEvidenceEnvelope(
            references=[
                {**reference, "id": f"conversation:conv-{index}:summary", "conversation_id": f"conv-{index}"}
                for index in range(25)
            ]
        )

    with pytest.raises(ValidationError, match="bounded transport limit"):
        ChatEvidenceEnvelope(references=[{**reference, "metadata": {"preview": "x" * 2_100}}])


def test_unknown_and_future_evidence_is_preserved_but_non_actionable() -> None:
    unknown = ChatEvidenceEnvelope(references=[{"id": "future-ref", "kind": "future_kind", "state": "future_state"}])
    assert unknown.references[0].kind == "unknown"
    assert unknown.references[0].state == "unknown"

    future = ChatEvidenceEnvelope(
        schema_version=2,
        references=[
            {
                "id": "conversation:conv-1:summary",
                "kind": "conversation_summary",
                "state": "available",
                "conversation_id": "conv-1",
            }
        ],
    )
    assert future.references[0].kind == "unknown"
    assert future.references[0].state == "unknown"
    assert future.references[0].conversation_id == "conv-1"
