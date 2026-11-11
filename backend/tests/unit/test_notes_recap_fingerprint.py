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


def test_late_refresh_identity_pins_meaningful_fields_and_ignores_metadata():
    from copy import deepcopy
    from utils.other.daily_summary_refresh import fingerprint, REVISION_FIELDS

    assert REVISION_FIELDS == (
        'sync_content_revision',
        'content_revision',
        'notes_llm_output_hash',
        'summary_completed_at',
        'discarded',
        'deleted',
        'is_locked',
        'content_kind',
        'relevance_decision',
        'sync_relevance_user_kept',
    )
    row = {
        'id': 'synthetic',
        'structured': {
            'overview': 'Summary',
            'action_items': [{'description': 'Plan', 'completed': False}],
            'events': [{'title': 'Meet', 'created': False}],
        },
    }
    changed = deepcopy(row)
    changed.update(
        updated_at='later-server-time',
        revision=42,
        starred=True,
        folder_id='other',
        geolocation={'address': 'Resolved'},
        transcript_segments='opaque bytes',
    )
    changed['structured']['action_items'][0]['completed'] = True
    changed['structured']['events'][0]['created'] = True
    assert fingerprint([row]) == fingerprint([changed])
    changed['notes_llm_output_hash'] = 'new-content'
    assert fingerprint([row]) != fingerprint([changed])
