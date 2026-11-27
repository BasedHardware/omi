"""Actual Commit protobuf coverage, including erasure and source preconditions."""

from google.cloud.firestore_v1.types import Document, DocumentMask, Precondition, Value, Write

from database import home_feed_writer as writer
from database.batch_privacy_write_fence import augment_commit

OWNER = 'projects/p/databases/(default)/documents/users/u'


def update(family='conversations', cid='c', **fields):
    return Write(
        update=Document(name=f'{OWNER}/{family}/{cid}', fields=fields),
        update_mask=DocumentMask(field_paths=list(fields)),
        current_document=Precondition(exists=True),
    )


def test_source_preconditions_positions_and_fields_are_preserved():
    source = update(user_title=Value(string_value='New title'))
    request, count = augment_commit({'database': 'projects/p/databases/(default)', 'writes': [source]})
    assert count == 1
    assert request.writes[0].update.fields['user_title'] == source.update.fields['user_title']
    assert source.update_mask.field_paths == ['user_title']
    assert set(request.writes[0].update_mask.field_paths) == {
        'user_title',
        'home_source_version',
        writer.LIST_TRANSCRIPT,
        writer.LIST_SOURCE_VERSION,
    }
    assert request.writes[0].current_document.exists
    receipt = next(write for write in request.writes[1:] if write.update.name == f'{OWNER}/episode_links/c')
    assert receipt.update.fields['home_dirty'].boolean_value
    control = next(write for write in request.writes if write.update.name == f'{OWNER}/episode_links/{writer.CONTROL}')
    assert control.update.fields['ready'].boolean_value is False


def test_prepare_home_only_writes_do_not_dirty_themselves():
    source = update(home_display=Value(string_value='sealed'), home_prepared=Value(boolean_value=True))
    assert writer.augment_home_writes([source]) == [source]


def test_live_title_claim_leaves_home_ready_but_publication_invalidates_it():
    state = Value(string_value='attempted')
    claim = update(v3_live_title_state=state)
    assert writer.augment_home_writes([claim]) == [claim]

    publication = update(v3_live_title_state=state, structured=Value(map_value={}))
    assert len(writer.augment_home_writes([publication])) > 1


def test_additive_live_append_and_progress_do_not_require_repreparation():
    progress = update(last_speech_at=Value(timestamp_value={'seconds': 1}))
    append = update(home_append_only=Value(boolean_value=True), transcript_segments=Value(string_value='encrypted'))
    writes = writer.augment_home_writes([progress, append])
    assert len(writes) == 2
    assert writes[0] == progress
    assert set(writes[1].update_mask.field_paths) == {
        'home_append_only',
        'transcript_segments',
        writer.LIST_TRANSCRIPT,
        writer.LIST_SOURCE_VERSION,
    }
    request, count = augment_commit({'database': 'projects/p/databases/(default)', 'writes': [append]})
    assert count == 1 and request.writes[0] == writes[1]
    renamed = update(home_append_only=Value(boolean_value=True), user_title=Value(string_value='edited'))
    assert len(writer.augment_home_writes([renamed])) > 1


def test_upload_custody_progress_preserves_home_but_combined_content_edits_invalidate():
    sessions = Value(map_value={'fields': {'live': Value(boolean_value=True)}})
    for fields in (
        {'record_upload_sessions': sessions},
        {'record_upload_sessions.live': Value(boolean_value=False)},
        {'record_upload_sessions': sessions, 'audio_files': Value(array_value={'values': []})},
    ):
        source = update(**fields)
        assert writer.augment_home_writes([source]) == [source]
    edited = update(record_upload_sessions=sessions, user_title=Value(string_value='edited'))
    assert len(writer.augment_home_writes([edited])) > 1


def test_transcript_redaction_invalidates_old_source_display_until_fresh_notes():
    source = update(transcript_segments=Value(string_value='redacted'))
    writes = writer.augment_home_writes([source])
    patch = next(write for write in writes if write.update.name == source.update.name)
    assert patch.update.fields['home_content_invalidated'].boolean_value is True


def test_root_delete_never_resurrects_user_subtree():
    source = Write(delete=f'{OWNER}/conversations/c')
    root = Write(delete=OWNER)
    assert writer.augment_home_writes([source, root]) == [source, root]


def test_staged_account_wipe_suppresses_receipts_on_every_source_delete_and_restores_context():
    source = Write(delete=f'{OWNER}/conversations/c')
    episode = Write(delete=f'{OWNER}/episodes/e')

    @writer.suppress_during_account_erasure
    def erase(uid):
        assert writer.augment_home_writes([source, episode]) == [source, episode]

    erase('u')
    assert len(writer.augment_home_writes([source])) > 1


def test_root_privacy_and_subscription_mutations_invalidate_full_policy():
    root = Write(
        update=Document(name=OWNER, fields={'data_protection_level': Value(string_value='enhanced')}),
        update_mask=DocumentMask(field_paths=['data_protection_level']),
        current_document=Precondition(exists=True),
    )
    writes = writer.augment_home_writes([root])
    assert any(
        write.update.fields.get('policy_dirty') and write.update.fields['policy_dirty'].boolean_value
        for write in writes
    )
    subscription = update('subscriptions', 's', status=Value(string_value='expired'))
    assert len(writer.augment_home_writes([subscription])) > 1


def test_compact_evidence_binds_to_the_same_write_and_is_cleared_on_replacement():
    source = update(
        transcript_segments=Value(string_value='encrypted'),
        **{writer.LIST_TRANSCRIPT: Value(string_value='encrypted-prefix')},
    )
    stamped = writer.augment_home_writes([source])[0]
    assert stamped.update.fields[writer.LIST_SOURCE_VERSION] == stamped.update.fields['home_source_version']
    assert stamped.update.fields[writer.LIST_TRANSCRIPT].string_value == 'encrypted-prefix'

    replaced = writer.augment_home_writes([update(transcript_segments=Value(string_value='changed'))])[0]
    for field in (writer.LIST_TRANSCRIPT, writer.LIST_SOURCE_VERSION):
        assert field in replaced.update_mask.field_paths
        assert field not in replaced.update.fields
