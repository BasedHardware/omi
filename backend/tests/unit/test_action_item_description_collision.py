"""Action-item endpoints must not let two items with identical description text corrupt
each other.

DeleteActionItemRequest/UpdateActionItemDescriptionRequest identify an action item by its
description text (no id/index), and the standalone action_items collection mirror step
in set_action_item_status looked items up the same way. Before this fix, all three
handlers applied their mutation (complete/rename/delete) to EVERY item sharing that
description instead of just the one the user acted on:

  - set_action_item_status's mirror step iterated every standalone id matching a
    description and marked all of them completed/incomplete.
  - update_action_item_description's mirror step renamed every standalone item matching
    old_description, not just the one embedded item that was actually renamed (which
    itself stops at the first match).
  - delete_action_item filtered ALL embedded items matching the description out of the
    conversation (list-comprehension over the full list) and deleted every matching
    standalone item too.

A conversation with two "Follow up" action items: completing/renaming/deleting one via
the app silently mutated or destroyed the other. The fix consumes/matches at most one
item per description occurrence instead of fanning a single request out to every match.

Source-level structural check: routers/conversations.py has a very heavy import graph
(Firestore, Pinecone vector_db, storage), matching the approach used elsewhere in this
suite for similar files (test_payment_stripe_refresh_idor.py, etc).
"""

from pathlib import Path

CONVERSATIONS_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "conversations.py"


def _source() -> str:
    return CONVERSATIONS_SOURCE.read_text(encoding="utf-8")


def _function_body(source: str, def_line: str, next_marker: str) -> str:
    start = source.index(def_line)
    end = source.index(next_marker, start + 1)
    return source[start:end]


def test_set_action_item_status_mirror_consumes_one_id_per_match():
    source = _source()
    body = _function_body(source, "def set_action_item_status", "\ndef update_action_item_description")

    assert "ids.pop(0)" in body, (
        "set_action_item_status's mirror step must consume one id per description match "
        "(ids.pop(0)), not iterate over every id sharing that description"
    )
    assert "for action_item_id in ids:" not in body, (
        "set_action_item_status must not fan a single completion update out to every "
        "standalone item sharing the description"
    )


def test_update_action_item_description_mirror_stops_at_first_match():
    source = _source()
    body = _function_body(source, "def update_action_item_description", "\ndef delete_action_item")

    # Two loops touch action items in this function: the embedded-list rename (already
    # breaks on first match) and the standalone mirror rename, which must also stop
    # after renaming exactly one standalone item.
    assert body.count("break") >= 2, (
        "both the embedded-list rename loop and the standalone mirror rename loop must "
        "stop after the first description match"
    )


def test_delete_action_item_removes_only_one_embedded_match():
    source = _source()
    body = _function_body(source, "def delete_action_item", "\n@router.")

    assert "delete_index" in body, (
        "delete_action_item must locate a single matching embedded item (delete_index), "
        "not filter every item sharing the description out of the conversation at once"
    )
    assert (
        "[item for item in action_items if not (item.description == data.description)]" not in body
    ), "delete_action_item must not remove every embedded item sharing the description in one pass"


def test_delete_action_item_mirror_stops_at_first_match():
    source = _source()
    body = _function_body(source, "def delete_action_item", "\n@router.")

    mirror_start = body.index("Mirror deletion")
    mirror_body = body[mirror_start:]
    assert "break" in mirror_body, "the standalone mirror deletion loop must stop after the first match"
