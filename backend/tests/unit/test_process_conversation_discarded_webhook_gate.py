"""Discarded conversations must not fire the developer 'conversation created' webhook.

should_discard_conversation marks noise/empty conversations as discarded=True, and the
app never surfaces them to the user. Before this fix, the webhook-scheduling block in
process_conversation sat at the same indentation as (but textually after, and outside)
the `if not discarded:` guard that already gates analytics/app-triggering/memory
extraction/vector indexing - so a discarded conversation still notified external
developer webhooks about a "conversation created" event for content the user never sees.

Source-level structural check: utils/conversations/process_conversation.py has a very
heavy import graph (LLM calls, Firestore, vector DB, app-triggering).
"""

from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parents[2] / "utils" / "conversations" / "process_conversation.py"


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_webhook_dispatch_is_gated_on_not_discarded():
    source = _source()
    webhook_call_pos = source.index("conversation_created_webhook(uid, conversation)")

    # Walk backwards from the webhook call to the nearest enclosing `if` at the same
    # indentation level as `if not is_reprocess:` to find its guard condition.
    preceding = source[:webhook_call_pos]
    guard_pos = preceding.rindex("if not is_reprocess")
    guard_line = source[guard_pos : source.index("\n", guard_pos)]

    assert "discarded" in guard_line, (
        "the conversation_created_webhook dispatch must be gated on `not discarded` (in addition to "
        "`not is_reprocess`), or discarded/noise conversations notify external developer webhooks "
        "about content the app never shows the user"
    )
    assert "not discarded" in guard_line
