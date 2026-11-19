"""Lifecycle-owned no-speech restore, independent of audio/secret dependencies.

This is the restore part of lifecycle.py's public boundary. Only the matching
storage generation may become visible again; restoration admits no cloud work.
"""

from typing import Any

from database import no_speech_terminal as no_speech_terminal_db


def restore_no_speech_capture(
    uid: str,
    conversation_id: str,
    *,
    expected_closed_revision: str,
    run_id: str,
    firestore_client: Any = None,
) -> None:
    """Restore only the unchanged generation this run closed."""
    no_speech_terminal_db.restore_no_speech(
        uid,
        conversation_id,
        expected_closed_revision=expected_closed_revision,
        run_id=run_id,
        firestore_client=firestore_client,
    )
