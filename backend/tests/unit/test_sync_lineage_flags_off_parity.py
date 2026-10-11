"""Two sync switches OFF match frozen main at persisted and intake boundaries."""

import hashlib
import json
import logging
import sys
import threading
import types
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.unit import test_sync_lineage_dedupe_replay as helpers
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_lineage_overlap import overlap_rows, straddling_rows
from tests.unit.test_sync_recording_lineage import ORIGIN, spans, sync_chunk
from utils.sync import assignment, recording_lineage

BASE = '35238e1dbeb6bb59821e5d01e281eb26d7dfbf0d'
SNAPSHOT = Path(__file__).parent / 'fixtures' / 'sync_lineage_main_parity.json'
FLAGS = (
    'SYNC_LINEAGE_LIVE_DEDUPE_ENABLED',
    'SYNC_WAL_AUDIO_COVERAGE_ENABLED',
    'SYNC_LINEAGE_S1_REQUIRED',
    'LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED',
)


def _source(path):
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    assert snapshot['revision'] == BASE
    source = snapshot['sources'][path]
    assert hashlib.sha256(source.encode()).hexdigest() == snapshot['sha256'][path]
    return source


def _load(name, source, monkeypatch, namespace=None):
    module = types.ModuleType(name)
    if namespace is not None:
        module.__dict__.update(namespace)
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(source, name, 'exec', flags=0x1000000), module.__dict__)
    return module


def _normalize(value):
    if isinstance(value, datetime):
        return {'datetime': value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(type(value).__name__)


def _bytes(value):
    return json.dumps(_normalize(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _rows(store):
    return [{'path': list(key), 'row': value} for key, value in sorted(store.rows.items())]


def _intake(module, store, incoming, *, candidate_id=None, target_id=None):
    return module.assign_in_transaction(
        store.transaction(),
        store.collection('users').document('u'),
        incoming,
        candidate_id=candidate_id,
        target_id=target_id,
        decode=deepcopy,
        encode=deepcopy,
        invalidate=lambda payload: None,
    )


def _drive(module, patch, store, texts, assignment_module, capture_enabled):
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import lifecycle

    patch.setattr(module, 'get_syncing_file_temporal_signed_url', lambda _path: 'file://x')
    patch.setattr(module, 'schedule_syncing_temporal_file_deletion', lambda _path: None)
    patch.setattr(module, 'get_prerecorded_service', lambda _lang: ('deepgram', 'cfg', 'nova-3'))
    patch.setattr(module, 'prerecorded', lambda *args, **kwargs: (['w'], 'en'))
    patch.setattr(
        module,
        'postprocess_words',
        lambda *args, **kwargs: [
            TranscriptSegment(
                id=f'stable-{i}',
                text=text,
                start=i * 10.0 + 0.7,
                end=i * 10.0 + 10.7,
                speaker='SPEAKER_00',
                is_user=False,
                speaker_id=0,
            )
            for i, text in enumerate(texts)
        ],
    )
    patch.setattr(module, 'get_timestamp_from_path', lambda _path: helpers.T0 + 40)
    patch.setattr(module, 'identify_speakers_for_segments', lambda *args, **kwargs: None)
    patch.setattr(module.conversations_db, 'get_manual_speaker_receipt', lambda *args: {})
    patch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, **kwargs: _intake(assignment_module, store, incoming, **kwargs),
    )
    finish = MagicMock()
    patch.setattr(module, 'finish_sync_segment', finish)
    response = {'new_memories': set(), 'updated_memories': set()}
    mapping = {
        'claim': {
            'capture_root': '00000000-0000-4000-8000-000000000001',
            'clock_epoch': 0,
            'rate_hz': 16000,
            'channel': 'mono',
            'codec': 'pcm16',
            'source_frame_start': 0,
            'frame_count': len(texts) + 2,
        },
        'offsets': [i * 160000 for i in range(len(texts) + 3)],
        'incomplete': False,
    }
    ok = module.process_segment(
        '/tmp/wal.wav',
        'u',
        response,
        threading.Lock(),
        [],
        target_conversation_id=helpers.LIVE_ID,
        client_device_id='pendant',
        lineage_binding='stamp_fallback',
        source_position_map=(mapping, 0) if capture_enabled else None,
    )
    return ok, response, finish


@pytest.fixture(autouse=True, params=['off', 'disabled-typo'])
def off(monkeypatch, request):
    for flag in FLAGS:
        monkeypatch.setenv(flag, request.param)
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'false')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)


@pytest.fixture
def frozen(monkeypatch):
    from utils.sync import pipeline

    assert callable(pipeline.process_segment)
    return (
        _load('frozen_main_assignment', _source('backend/utils/sync/assignment.py'), monkeypatch),
        _load('frozen_main_lineage', _source('backend/utils/sync/recording_lineage.py'), monkeypatch),
    )


@pytest.mark.parametrize('kind', ['mixed40', 'mixed1200', 'all_repeat', 'same_range', 'new_row', 'pinned'])
def test_assignment_payload_result_and_survivors_are_byte_identical_to_main(frozen, kind):
    old, _ = frozen
    row = helpers.live_row()
    if kind == 'pinned':
        row['audio_timeline'] = {'version': 2}
    texts = [helpers.reworded(text) for text in helpers.LIVE]
    if kind in ('mixed40', 'mixed1200', 'new_row', 'pinned'):
        texts += helpers.NEW
    incoming = helpers.wal(1200 if kind == 'mixed1200' else 40, texts)
    if kind == 'same_range':
        incoming = helpers.wal_at(helpers.T0, [helpers.LIVE[0]], 10.0)
    if kind == 'pinned':
        incoming = helpers.wal(-40, helpers.NEW)
    incoming['_sync_lineage_binding'] = 'stamp_fallback'
    helpers.prove(incoming, row)
    outputs = []
    for module in (old, assignment):
        store = helpers.seeded_store([] if kind == 'new_row' else [row])
        candidate = deepcopy(incoming)
        if module is old:
            candidate.pop('_sync_lineage_binding')
        result = _intake(module, store, candidate, target_id=None if kind == 'new_row' else row['id'])
        outputs.append(_bytes({'result': result, 'rows': _rows(store)}))
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize('stamp', [None, 'GEN-A', 'GEN-B', 'UNRELATED'])
@pytest.mark.parametrize('kind', ['strict', 'tolerant'])
def test_overlap_targets_counts_and_log_bytes_match_main(frozen, stamp, caplog, kind):
    _, old = frozen
    rows, span = (overlap_rows(), (44300, 44330)) if kind == 'strict' else (straddling_rows(), (44399, 44410))
    chunk = sync_chunk(span[0], span[1], 'synthetic buffered speech before creation')
    output, messages = [], []
    for module in (old, recording_lineage):
        plan = module.select_segment_targets(
            rows,
            ORIGIN,
            spans([chunk]),
            stamped_target=stamp,
            source='omi',
            client_device_id='pendant',
            is_locked=False,
        )
        output.append(
            _bytes(
                {
                    key: getattr(plan, key)
                    for key in ('targets', 'outcome', 'reason', 'counts', 'generations', 'rows', 'degraded')
                }
            )
        )
        caplog.clear()
        with caplog.at_level(logging.INFO):
            module._emit(plan, 'synthetic-job')
        messages.append(_bytes([record.getMessage() for record in caplog.records]))
    assert output[0] == output[1]
    assert messages[0] == messages[1]


@pytest.mark.parametrize('rows', [[], overlap_rows()])
def test_resolver_read_calls_results_and_logs_match_main(frozen, monkeypatch, caplog, rows):
    from database import sync_recording_lineage as db

    _, old = frozen
    result = []
    for module in (old, recording_lineage):
        with monkeypatch.context() as patch:
            query = MagicMock(return_value=deepcopy(rows))
            origin = MagicMock(return_value=[])
            probe = MagicMock(return_value=None)
            patch.setattr(db, 'get_recording_generations', query)
            patch.setattr(db, 'get_origin_generation', origin)
            patch.setattr(db, 'get_recording_id_probe', probe)
            caplog.clear()
            with caplog.at_level(logging.INFO):
                targets = module.resolve_segment_targets(
                    'u',
                    ORIGIN,
                    {'s': (44300, 44330)},
                    stamped_target=None,
                    source='omi',
                    client_device_id='pendant',
                    is_locked=False,
                    job_id='synthetic-job',
                )
            probe.assert_not_called()
            calls = [
                [{'args': call.args, 'kwargs': call.kwargs} for call in mock.call_args_list] for mock in (query, origin)
            ]
            result.append(
                _bytes({'targets': targets, 'calls': calls, 'logs': [r.getMessage() for r in caplog.records]})
            )
    assert result[0] == result[1]


@pytest.mark.parametrize('capture_enabled', [False, True])
@pytest.mark.parametrize('texts', [helpers.NEW, [helpers.reworded(text) for text in helpers.LIVE]])
def test_process_segment_saved_rows_results_finish_and_log_bytes_match_main(
    frozen, monkeypatch, caplog, texts, capture_enabled
):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true' if capture_enabled else 'false')
    from utils import capture_evidence, metrics
    from utils.sync import pipeline

    old_assignment, _ = frozen
    module = _load('frozen_main_process', _source('process_segment'), monkeypatch, pipeline.__dict__)
    for name in ('bounded_envelope', 'merge_track_receipts', 'sync_segment_receipt', 'unknown_envelope'):
        module.__dict__[name] = getattr(capture_evidence, name)
    module.OMI_CAPTURE_EVIDENCE_ENVELOPES_TOTAL = metrics.OMI_CAPTURE_EVIDENCE_ENVELOPES_TOTAL
    original = module.process_segment

    def old_process(*args, lineage_binding=None, **kwargs):
        assert lineage_binding == 'stamp_fallback'
        return original(*args, **kwargs)

    module.process_segment = old_process
    outputs = []
    for process_module, assignment_module in ((module, old_assignment), (pipeline, assignment)):
        store = helpers.seeded_store([helpers.live_row()])
        with monkeypatch.context() as patch:
            caplog.clear()
            with caplog.at_level(logging.INFO):
                ok, response, finish = _drive(process_module, patch, store, texts, assignment_module, capture_enabled)
            calls = [
                {'args': [call.args[0], call.args[1], call.args[2], call.args[4]], 'kwargs': call.kwargs}
                for call in finish.call_args_list
            ]
            outputs.append(
                _bytes(
                    {
                        'ok': ok,
                        'response': response,
                        'rows': _rows(store),
                        'finish': calls,
                        'logs': [record.getMessage() for record in caplog.records],
                    }
                )
            )
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize('capture_enabled', [False, True])
@pytest.mark.asyncio
async def test_audio_consumer_off_preserves_inputs_without_lookup_or_log(monkeypatch, caplog, capture_enabled):
    from utils.sync import wal_audio_coverage as coverage

    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true' if capture_enabled else 'false')
    paths = ['synthetic.wav']
    maps = {'synthetic.wav': {'claim': {}, 'offsets': [0, 160]}} if capture_enabled else {}
    monkeypatch.setattr(coverage, 'build_sync_source_frame_maps', lambda *args: maps)
    executor = MagicMock()
    with caplog.at_level(logging.INFO):
        result = await coverage.apply_sync_wal_audio_coverage(
            'u',
            'omi',
            False,
            'pendant',
            ORIGIN,
            {'synthetic.bin': {}},
            paths,
            {},
            run_blocking=executor,
            db_executor=None,
            storage_executor=None,
            cleanup_files=MagicMock(),
        )
    assert result[0] is paths and result[1] is maps and result[2] is False
    executor.assert_not_called()
    assert not caplog.records


def test_excluded_cohort_stays_main_even_with_both_flags_on(frozen, monkeypatch):
    for flag in FLAGS:
        monkeypatch.setenv(flag, 'on')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'someone-else')
    old, _ = frozen
    outputs = []
    row = helpers.live_row()
    incoming = helpers.wal(40, [helpers.reworded(text) for text in helpers.LIVE] + helpers.NEW)
    helpers.prove(incoming, row)
    for module in (old, assignment):
        store = helpers.seeded_store([row])
        result = _intake(module, store, deepcopy(incoming), target_id=helpers.LIVE_ID)
        outputs.append(_bytes({'result': result, 'rows': _rows(store)}))
    assert outputs[0] == outputs[1]
    assert recording_lineage.lineage_resolution_requested('u', ORIGIN, 1500, 1510) is False
