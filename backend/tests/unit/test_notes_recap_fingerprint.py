"""Recap refresh uses canonical conversation IDs/revisions, with no transcript reads."""

from utils.llm.daily_recap_fingerprint import input_fingerprint


def test_conversation_order_is_irrelevant_but_ids_and_revisions_are_not():
    rows = [{'id': 'synthetic-a', 'sync_content_revision': 1}, {'id': 'synthetic-b', 'sync_content_revision': 3}]
    fingerprint = input_fingerprint(rows)
    assert fingerprint == input_fingerprint(rows[::-1])
    assert fingerprint != input_fingerprint(rows[:1])
    assert fingerprint != input_fingerprint([dict(rows[0], sync_content_revision=2), rows[1]])


def test_legacy_reprocessing_changes_summary_fingerprint_without_version_field():
    before = [{'id': 'synthetic-a', 'structured': {'title': 'Workshop', 'overview': 'Original synthetic overview'}}]
    after = [{'id': 'synthetic-a', 'structured': {'title': 'Workshop', 'overview': 'Revised synthetic overview'}}]
    assert input_fingerprint(before) != input_fingerprint(after)
    assert input_fingerprint(before) == input_fingerprint([dict(before[0], transcript_segments='opaque bytes')])
