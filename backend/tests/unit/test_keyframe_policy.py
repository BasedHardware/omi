from datetime import datetime, timezone

from utils.retrieval.keyframe_policy import (
    KeyframeCandidate,
    select_conversation_keyframe,
)


def test_keyframe_selection_is_latest_complete_and_deterministic():
    selected = select_conversation_keyframe(
        [
            KeyframeCandidate("early", datetime(2026, 8, 24, 10, tzinfo=timezone.utc), "Editor", content_hash="a"),
            KeyframeCandidate("late", datetime(2026, 8, 24, 11, tzinfo=timezone.utc), "Editor", content_hash="b"),
            KeyframeCandidate(
                "incomplete",
                datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
                "Editor",
                content_hash="c",
                capture_complete=False,
            ),
        ]
    )
    assert selected is not None
    assert selected.frame_id == "late"
    assert selected.retention_class == "conversation_lifetime"
    assert selected.expires_at is None


def test_excluded_and_empty_candidates_never_become_conversation_evidence():
    assert (
        select_conversation_keyframe(
            [
                KeyframeCandidate("excluded", datetime.now(timezone.utc), "Secrets", content_hash="x", excluded=True),
                KeyframeCandidate("no-hash", datetime.now(timezone.utc), "Editor"),
            ]
        )
        is None
    )
