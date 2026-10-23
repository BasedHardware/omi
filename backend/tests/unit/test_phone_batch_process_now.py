"""Selected phone and Watch recovery uploads retain the user's keep intent.

Exercise the production job coordinator and relevance handoff with external
storage/STT replaced. Intake has already retained the short transcript; it must
be restored before enrichment, even when rule-discard intake enrolled no work.
"""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules
from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes, _prepare
from utils.conversations.relevance import decide_relevance


@pytest.fixture(scope='module')
def pipeline():
    with stub_modules(_build_pipeline_fakes()):
        yield load_module_fresh(
            'utils.sync.pipeline', str(Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py')
        )


EXPLICIT = '/tmp/audio_omibatchphone_opus_fs320_16000_1_fs320_1720000000.bin'
AUTO = '/tmp/audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000000.bin'
WATCH = '/tmp/audio_omibatchwatch0123456789abcdef0123456789abcdefs0_pcm16_16000_1_fs160_1720000000.bin'


def prepare_recording(pipeline, *, discarded=True):
    reprocess = pipeline._reprocess_merged_conversations
    _prepare(pipeline, ['/tmp/1720000000.wav'])
    pipeline._reprocess_merged_conversations = reprocess

    async def resolve_location(value):
        return value

    pipeline.async_resolve_geolocation = resolve_location
    pipeline.schedule_person_voice_learning_retries = MagicMock()
    row = {
        'id': 'recording',
        'status': 'completed',
        'discarded': discarded,
        'sync_relevance': 'review' if discarded else 'keep',
        'language': 'en',
        'source': 'phone',
        'transcript_segments': [{'text': 'Testing one two three.', 'start': 0, 'end': 3}],
    }

    def ingest(_path, _uid, response, _lock, _errors, *args, **kwargs):
        response['new_memories'].add(row['id'])
        if not discarded:
            response.setdefault('_merged', {})[row['id']] = 'en'
        return True

    pipeline.process_segment = ingest
    pipeline.conversations_db.get_conversation = lambda *args: deepcopy(row)
    pipeline.deserialize_conversation = lambda data: SimpleNamespace(**data)

    def restore(*args):
        row.update(discarded=False, sync_relevance='keep', sync_relevance_user_kept=True)
        return True

    pipeline.lifecycle_service.restore_discarded = MagicMock(side_effect=restore)

    def process(**kwargs):
        conversation = kwargs['conversation']
        decision = decide_relevance(
            trigger=kwargs['trigger'],
            texts=[s['text'] for s in conversation.transcript_segments],
            speech_seconds=3,
            has_photos=False,
            user_kept=kwargs['user_kept'],
            exempt=False,
            trusted_wake_word=False,
            model_discards=lambda *_args: True,
            calendar_retains=lambda: False,
        )
        conversation.discarded = decision.discard
        row.update(discarded=decision.discard, relevance_decision=decision.as_record())
        return conversation

    pipeline.process_conversation = MagicMock(side_effect=process)
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize('discarded', [True, False])
@pytest.mark.parametrize('path,source', [(EXPLICIT, 'phone'), (WATCH, 'omi')])
async def test_process_now_keeps_selected_recording_before_enrichment(pipeline, discarded, path, source):
    row = prepare_recording(pipeline, discarded=discarded)

    await pipeline._run_full_pipeline_background_async('job', 'uid', [path], source, False, '/tmp/job')

    pipeline.lifecycle_service.restore_discarded.assert_called_once_with('uid', 'recording')
    pipeline.process_conversation.assert_called_once()
    assert pipeline.process_conversation.call_args.kwargs['user_kept'] is True
    assert row['discarded'] is False
    assert row['relevance_decision']['decided_by'] == 'user'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'paths',
    [
        [AUTO],
        [EXPLICIT, AUTO],
        [EXPLICIT, EXPLICIT],
        ['/tmp/audio_phonemic_pcm16_1.bin'],
        [WATCH, WATCH],
        [WATCH, AUTO],
        [WATCH.replace('0123456789abcdef0123456789abcdef', 'invalid')],
    ],
)
async def test_automatic_or_mixed_uploads_keep_existing_discard_policy(pipeline, paths):
    row = prepare_recording(pipeline)

    await pipeline._run_full_pipeline_background_async('job', 'uid', paths, 'phone', False, '/tmp/job')

    pipeline.lifecycle_service.restore_discarded.assert_not_called()
    assert row['discarded'] is True


def test_failed_keep_write_is_not_acknowledged_as_success(pipeline):
    prepare_recording(pipeline)
    pipeline.lifecycle_service.restore_discarded.side_effect = RuntimeError('storage unavailable')

    with pytest.raises(RuntimeError, match='storage unavailable'):
        pipeline._reprocess_merged_conversations(
            'uid', {'new_memories': {'recording'}, 'updated_memories': set()}, user_selected=True
        )


def test_deleted_selected_recording_is_fenced_without_resurrection(pipeline):
    prepare_recording(pipeline)
    pipeline.lifecycle_service.restore_discarded.side_effect = None
    pipeline.lifecycle_service.restore_discarded.return_value = False
    response = {'new_memories': {'recording'}, 'updated_memories': set()}

    pipeline._reprocess_merged_conversations('uid', response, user_selected=True)

    assert response['new_memories'] == set()
    pipeline.process_conversation.assert_not_called()
