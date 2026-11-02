"""Synthetic fixtures for one media policy across independent derived consumers."""

from copy import deepcopy
from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.refactor_modes import uid_digest
from config.policy import ProjectionPolicy
from database import conversations
from utils.batch_pipeline import projection
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.conversations import media_consumers, owner_attribution, relevance_content
from utils.memory import required_source_admission as admission

UID = 'synthetic-feedback-owner'
NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)
FLAG = relevance_content.FLAG


@pytest.fixture(autouse=True)
def clean_policy(monkeypatch):
    for flag in (FLAG, 'SPEAKER_EVIDENCE_MODE'):
        for suffix in ('', '_SERVE_PERCENT', '_SERVE_UID_SHA256S', '_SHADOW_PERCENT'):
            monkeypatch.delenv(flag + suffix, raising=False)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    monkeypatch.setenv(FLAG + '_SHADOW_PERCENT', '100')
    monkeypatch.setattr(admission, 'assert_account_active', lambda *a: None)


def item(source_ids=('source',), *, explicit=False):
    return SimpleNamespace(
        user_asserted=explicit,
        evidence=[
            SimpleNamespace(
                source_type='conversation',
                conversation_id=sid,
                source_id=sid,
                quote_refs=[{'text': 'I prefer tea', 'segment_id': 'owner'}],
            )
            for sid in source_ids
        ],
    )


def source(kind=None):
    return {
        'id': 'source',
        'content_kind': kind,
        'transcript_segments': [
            dict(
                id='owner',
                text='I prefer tea',
                start=0,
                end=5,
                speaker_id=0,
                speaker_id_scope='sync:fixture',
                is_user=True,
                speaker_label_source='auto',
                speaker_identity_status='user',
                speaker_match_source='conversation_voice',
            ),
            dict(
                id='other',
                text='I prefer coffee',
                start=5,
                end=10,
                speaker_id=1,
                speaker_id_scope='sync:fixture',
                is_user=False,
            ),
        ],
    }


def client_for(monkeypatch, rows):
    reads = []

    def document(path):
        reads.append(path)
        return SimpleNamespace(
            get=lambda: SimpleNamespace(update_time=NOW, to_dict=lambda: rows.get(path.rsplit('/', 1)[-1]))
        )

    monkeypatch.setattr(conversations, 'prepare_conversation_for_read', lambda row, *a, **k: deepcopy(row))
    return SimpleNamespace(document=document), reads


@pytest.mark.parametrize('speaker_mode', ['off', 'shadow', 'serve'])
@pytest.mark.parametrize('media_mode,blocked', [('off', False), ('shadow', False), ('serve', True)])
@pytest.mark.parametrize('kind', ['media', 'noise'])
def test_required_memory_media_is_independent_of_speaker_mode(monkeypatch, speaker_mode, media_mode, blocked, kind):
    monkeypatch.setenv(FLAG, media_mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', speaker_mode)
    row = source(kind)
    before = deepcopy(row)
    client, reads = client_for(monkeypatch, {'source': row})
    result = admission.source_revisions(UID, item(), db_client=client)
    assert (result is None) is blocked
    assert row == before
    assert len(reads) == int(media_mode != 'off' or speaker_mode == 'serve')
    if media_mode == 'shadow' and speaker_mode != 'serve':
        assert result == {}  # No shadow revision fences or derived-write changes.


def test_media_does_not_promote_owner_identity_and_reuses_p2_roles(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    row = source()
    row['transcript_segments'][0]['speaker_label_source'] = 'carried'
    client, _ = client_for(monkeypatch, {'source': row})
    assert admission.source_revisions(UID, item(), db_client=client) is not None
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    assert admission.source_revisions(UID, item(), db_client=client) is None
    row['transcript_segments'][0]['speaker_label_source'] = 'manual'
    roles = owner_attribution.speaker_role_map(row['transcript_segments'])
    assert [r.role for r in roles.roles] == ['primary_user', 'unknown']
    assert admission.source_revisions(UID, item(), db_client=client) is not None


def test_required_sources_read_each_document_once_and_cap_at_four(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    client, reads = client_for(monkeypatch, {str(i): source() for i in range(5)})
    revisions = admission.source_revisions(UID, item(('0', '0', '1', '2')), db_client=client)
    assert len(revisions) == len(reads) == 3
    reads.clear()
    assert admission.source_revisions(UID, item(('0',) * 5), db_client=client) == {f'users/{UID}/conversations/0': NOW}
    assert len(reads) == 1
    reads.clear()
    assert admission.source_revisions(UID, item(tuple(str(i) for i in range(5))), db_client=client) is None
    assert not reads
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'off')
    monkeypatch.setenv(FLAG, 'shadow')
    assert admission.source_revisions(UID, item(tuple(str(i) for i in range(5))), db_client=client) == {}
    assert not reads


@pytest.mark.parametrize('protection', ['restored', 'manual_owner', 'photos', 'user_title'])
@pytest.mark.parametrize('kind', ['media', 'noise'])
def test_current_user_authority_overrides_stale_media_for_every_consumer(monkeypatch, protection, kind):
    monkeypatch.setenv(FLAG, 'serve')
    row = source(kind)
    if protection == 'restored':
        row['sync_relevance_user_kept'] = True
    elif protection == 'manual_owner':
        row['transcript_segments'][0]['speaker_label_source'] = 'manual'
    elif protection == 'photos':
        row['photos'] = [{'id': 'synthetic-photo'}]
    else:
        row['user_title'] = 'Synthetic user title'
    before = deepcopy(row)
    for consumer in ('memories', 'daily_summary', 'recap', 'action_items'):
        assert not media_consumers.is_excluded(UID, row, consumer=consumer)
    client, reads = client_for(monkeypatch, {'source': row})
    assert admission.source_revisions(UID, item(), db_client=client) is not None
    assert len(reads) == 1 and row == before


@pytest.mark.parametrize('kind', ['media', 'noise'])
@pytest.mark.parametrize('speaker_mode', ['off', 'serve'])
def test_photo_marker_survives_real_prepare_read_without_fetching_subcollection(monkeypatch, kind, speaker_mode):
    monkeypatch.setenv(FLAG, 'serve')
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', speaker_mode)
    row = source(kind)
    row.update(has_photos=True, data_protection_level='standard')
    before = deepcopy(row)
    prepare = conversations.prepare_conversation_for_read
    client, reads = client_for(monkeypatch, {'source': row})
    monkeypatch.setattr(conversations, 'prepare_conversation_for_read', prepare)
    # Use the real undecorated production read boundary: photo contents remain
    # in their subcollection. This client cannot perform collection queries.
    prepared = prepare(row, UID, firestore_client=client)
    assert prepared['has_photos'] is True and not prepared.get('photos')
    for consumer in ('memories', 'daily_summary', 'recap', 'action_items'):
        assert not media_consumers.is_excluded(UID, prepared, consumer=consumer)
    assert admission.source_revisions(UID, item(), db_client=client) == {f'users/{UID}/conversations/source': NOW}
    assert len(reads) == 1 and row == before


@pytest.mark.parametrize('kind', ['media', 'noise'])
@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_photos_only_conversation_is_never_suppressed_by_media_gate(monkeypatch, kind, mode):
    monkeypatch.setenv(FLAG, mode)
    row = {'id': 'synthetic-photo-only', 'has_photos': True, 'content_kind': kind, 'transcript_segments': []}
    before = deepcopy(row)
    for consumer in ('memories', 'daily_summary', 'recap', 'action_items'):
        assert not media_consumers.is_excluded(UID, row, consumer=consumer)
    assert row == before


def test_manual_media_protection_keeps_the_existing_scoped_duration_floor(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    row = source('media')
    owner = row['transcript_segments'][0]
    owner['speaker_label_source'] = 'manual'
    owner['end'] = 1
    assert media_consumers.is_excluded(UID, row, consumer='memories')
    # A sibling of the manual excerpt is still not owner speech.
    row['transcript_segments'].append({**owner, 'id': 'sibling', 'speaker_label_source': 'carried', 'end': 600})
    assert media_consumers.is_excluded(UID, row, consumer='memories')
    owner['end'] = 6
    assert not media_consumers.is_excluded(UID, row, consumer='memories')


@pytest.mark.parametrize('unscoped', [False, True])
def test_uncertain_manual_owner_anchor_protects_without_promoting_identity(monkeypatch, unscoped):
    monkeypatch.setenv(FLAG, 'serve')
    row = source('media')
    owner = row['transcript_segments'][0]
    owner['speaker_label_source'] = 'manual'
    if unscoped:
        owner.pop('speaker_id')
    else:
        other = row['transcript_segments'][1]
        other.update(is_user=True, speaker_label_source='manual')
    assert all(role.role == 'unknown' for role in owner_attribution.speaker_role_map(row['transcript_segments']).roles)
    assert not media_consumers.is_excluded(UID, row, consumer='memories')


@pytest.mark.parametrize('media_mode', ['off', 'shadow', 'serve'])
def test_explicit_text_has_independent_authority_and_no_source_reads(monkeypatch, media_mode):
    monkeypatch.setenv(FLAG, media_mode)
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    client = SimpleNamespace(document=lambda *_: pytest.fail('explicit text read source'))
    assert admission.source_revisions(UID, item(explicit=True), db_client=client) == {}
    assert admission.source_revisions(UID, item(()), db_client=client) == {}


def test_shadow_source_errors_and_missing_rows_preserve_normalization(monkeypatch, caplog):
    monkeypatch.setenv(FLAG, 'shadow')

    def fail(*a):
        raise RuntimeError('PRIVATE_SOURCE_SENTINEL')

    client = SimpleNamespace(document=fail)
    with caplog.at_level(logging.INFO):
        assert admission.source_revisions(UID, item(), db_client=client) == {}
    assert 'reason=source_unavailable' in caplog.text
    assert UID not in caplog.text and 'PRIVATE_SOURCE_SENTINEL' not in caplog.text
    client, _ = client_for(monkeypatch, {})
    assert admission.source_revisions(UID, item(), db_client=client) == {}


def test_unsampled_shadow_sources_read_nothing(monkeypatch):
    monkeypatch.setenv(FLAG + '_SHADOW_PERCENT', '0')
    client = SimpleNamespace(document=lambda *_: pytest.fail('unsampled source read'))
    assert admission.source_revisions(UID, item(), db_client=client) == {}


@pytest.mark.parametrize('consumer', ['memories', 'daily_summary', 'recap', 'action_items'])
def test_consumer_shadow_observes_and_serving_cohort_matches_producer(monkeypatch, caplog, consumer):
    row = source('media')
    with caplog.at_level(logging.INFO):
        assert not media_consumers.is_excluded(UID, row, consumer=consumer)
    assert f'consumer={consumer} reason=media serving=false' in caplog.text
    monkeypatch.setenv(FLAG + '_SERVE_UID_SHA256S', uid_digest(UID))
    monkeypatch.setenv(FLAG + '_SHADOW_PERCENT', '0')
    assert media_consumers.is_excluded(UID, row, consumer=consumer)
    assert not media_consumers.is_excluded('other-synthetic-owner', row, consumer=consumer)
    monkeypatch.setenv(FLAG, 'off')
    assert not media_consumers.is_excluded(UID, row, consumer=consumer)


def test_summary_and_action_write_entrypoints_share_gate(monkeypatch):
    from utils.conversations.action_item_extraction import action_items_for_write

    row = SimpleNamespace(**source('media'))
    row.is_locked = False
    row.structured = SimpleNamespace(action_items=[])
    assert media_consumers.eligible_conversations(UID, [row]) == [row]
    monkeypatch.setenv(FLAG, 'serve')
    assert media_consumers.eligible_conversations(UID, [row]) == []
    assert action_items_for_write(UID, row, NOW, lambda *_: pytest.fail('excluded task write')) == []


def projected(text):
    binding = ProjectionBinding(UID, 'job', 'content', ('piece',))
    work = WorkItem('piece', UID, NOW.timestamp(), 'gs://synthetic/audio', 30, Priority.FRESH)
    payload = {
        'audio_seconds': 30,
        'speech_seconds': 4,
        'words': [{'word': text, 'timestamp': [2, 6]}],
        'diarization': {'turns': [{'start': 2, 'end': 6, 'speaker': 'SPEAKER_00'}]},
    }
    return work, binding, payload


@pytest.mark.parametrize('text', ['Subtitles by Synthetic Team', '[music]'])
def test_projected_sync_shadow_is_byte_identical_and_serving_uses_existing_rules(monkeypatch, caplog, text):
    work, binding, payload = projected(text)
    monkeypatch.setenv(FLAG, 'off')
    legacy = projection.build_incoming(work, binding, payload)
    monkeypatch.setenv(FLAG, 'shadow')
    with caplog.at_level(logging.INFO):
        shadow = projection.build_incoming(work, binding, payload)
    assert shadow == legacy
    assert 'event=batch_media_admission reason=' in caplog.text and 'serving=false' in caplog.text
    assert text not in caplog.text and UID not in caplog.text
    monkeypatch.setenv(FLAG + '_SERVE_PERCENT', '100')
    serving = projection.build_incoming(work, binding, payload)
    assert not serving['transcript_segments']
    assert serving['finished_at'] == legacy['finished_at']
    assert payload['words'][0]['word'] == text  # Retain original committed source.


@pytest.mark.parametrize(
    'text',
    [
        'Merhaba, yarın tekrar görüşelim.',
        'नमस्ते, कल फिर मिलते हैं।',
        'আমরা আগামীকাল আবার কথা বলব।',
        'Καλημέρα, ας μιλήσουμε αύριο.',
        'We can meet mañana после обеда.',
    ],
)
def test_real_multilingual_projected_speech_survives_without_owner_enrollment(monkeypatch, text):
    monkeypatch.setenv(FLAG, 'serve')
    work, binding, payload = projected(text)
    row = projection.build_incoming(work, binding, payload)
    assert row['transcript_segments'][0]['text'] == text
    assert row['transcript_segments'][0]['is_user'] is False
    assert not relevance_content.exclude_from_derived(UID, row, consumer='memories')


def test_all_filtered_projection_settles_without_assigning_or_retrying(monkeypatch):
    monkeypatch.setenv(FLAG, 'serve')
    work, binding, payload = projected('[music]')
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    session = projector.store.session.return_value
    session.persist_empty.return_value = {'state': 'ready', 'conversation_id': None}
    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', Mock())
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', Mock())
    projector.finish_part = Mock()
    projector.assign_parts(work, {'result': {'result_uri': 'fixture'}}, binding, policy=ProjectionPolicy())
    session.persist_empty.assert_called_once_with()
    projection.conversations_db.assign_sync_conversation.assert_not_called()
    projection.conversations_db.get_closest_conversation_to_timestamps.assert_not_called()
    projector.finish_part.assert_called_once()
    assert session.speech_seconds == 4  # Measured VAD accounting is not rewritten.
