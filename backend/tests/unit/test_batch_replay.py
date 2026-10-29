"""Replay gate must detect regressions and never export unapproved metadata."""

from copy import deepcopy
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testing.batch_replay.capture import sanitize
from testing.batch_replay.gate import compare
from testing.batch_replay.runner import geometry_boundaries, replay


def test_capture_constructs_allowlist_and_hashes_related_identities():
    salt = b'synthetic-per-corpus-salt'
    digest = lambda value: hmac.new(salt, value.encode(), hashlib.sha256).hexdigest() if value else None
    job = {
        'owner_id': 'private-owner',
        'duration_seconds': 1,
        'conversation_id': 'private-target',
        'transcript': 'must not escape',
        'email': 'must not escape',
        'retry_at': 'private-clock',
        'fresh_capture': False,
        'projection_binding': {'target_conversation_id': 'private-target'},
        'speech_spans': [{'start': 0.0, 'end': 1.0, 'text': 'must not escape'}],
        'manifest': {
            'references': [
                {'start_frame': 0, 'offset_frame': 2, 'frames': 3, 'source_frames': 5, 'path': 'must not escape'}
            ]
        },
    }
    entry = {
        'segment_id': 'private-unit',
        'previous_segment_id': 'private-predecessor',
        'projection_state': 'unknown-private-value',
    }
    unit = sanitize(
        job,
        entry,
        {'projection_watermark': 'private-predecessor'},
        {'status': 'completed', 'discarded': True, 'name': 'must not escape'},
        digest,
    )
    output = json.dumps(unit)
    assert 'private-' not in output and 'must not escape' not in output
    assert unit['target'] == unit['conversation'] == digest('private-target')
    assert unit['previous'] == unit['watermark']
    assert unit['projection_state'] == 'other' and unit['retry_present'] is True
    assert unit['lane'] == 'backfill'
    assert unit['references'] == [{'start_frame': 0, 'offset_frame': 2, 'frames': 3, 'source_frames': 5}]
    assert unit['spans'] == [{'start': 0.0, 'end': 1.0}]


def test_gate_detects_known_exception_spreading_and_chain_backlog_growth():
    baseline = {
        'exceptions': {'vad:ValueError:validator': 1},
        'unit_issues': {'a': ['vad:ValueError:validator']},
        'chain_blocks': [{'owner': 'owner', 'head': 'a', 'blocked_units': 1}],
    }
    candidate = deepcopy(baseline)
    candidate['unit_issues']['b'] = ['vad:ValueError:validator']
    candidate['chain_blocks'][0]['blocked_units'] = 2
    delta = compare(candidate, baseline)
    assert delta['regression'] and delta['new_unit_failures'] == {'b': ['vad:ValueError:validator']}
    assert len(delta['new_chain_blocks']) == 1 and not delta['new_exception_sites']
    assert not compare(baseline, baseline)['regression']


def test_gate_accepts_an_earlier_head_fix_that_exposes_a_later_existing_block():
    baseline = {
        'exceptions': {},
        'unit_issues': {},
        'chain_blocks': [{'owner': 'owner', 'head': 'a', 'blocked_units': 3, 'units': ['a', 'b', 'c']}],
    }
    candidate = {
        'exceptions': {},
        'unit_issues': {},
        'chain_blocks': [{'owner': 'owner', 'head': 'b', 'blocked_units': 2, 'units': ['b', 'c']}],
    }
    assert not compare(candidate, baseline)['regression']
    baseline['exceptions']['walk:Conflict:known'] = 1
    candidate['exceptions']['walk:Conflict:known'] = 1
    candidate['unit_issues']['b'] = ['walk:Conflict:known']
    assert not compare(candidate, baseline)['regression']
    assert compare(candidate, baseline)['newly_reached_known_failures'] == {'b': ['walk:Conflict:known']}
    candidate['exceptions']['walk:ValueError:new'] = 1
    candidate['unit_issues']['b'].append('walk:ValueError:new')
    assert compare(candidate, baseline)['regression']


def test_boundary_oracle_rejects_validators_that_accept_invalid_geometry():
    source = SimpleNamespace(MAGIC=b'synthetic', materialize=lambda *args: b'')

    def item(sid, owner, capture, uri, duration, priority, **kwargs):
        return SimpleNamespace(owner_id=owner, capture_at=capture, **kwargs)

    result = geometry_boundaries([{'duration': 1.0}], lambda *args: [], source, item, None)
    assert result['expected_rejections'] == 0
    assert len(result['failures']) == 4
    assert all(failure['exception'] == 'MissingExpectedRejection' for failure in result['failures'])


@pytest.fixture
def backend_tree():
    # Product imports belong to setup, just as backend conftest's other
    # service fixtures; the measured assertions below exercise replay itself.
    backend = Path(__file__).resolve().parents[2]
    replay({'units': []}, backend)
    return backend


def test_current_incident_shapes_clear(backend_tree):
    backend = backend_tree
    corpus = json.loads((backend / 'testing/batch_replay/regressions.json').read_text())
    healthy = replay(corpus, backend)
    assert healthy['persisted'] == len(corpus['units'])
    assert not healthy['exceptions'] and not healthy['chain_blocks']
    assert healthy['coverage']['followup_exercised'] == len(corpus['units'])
    assert healthy['coverage']['source_validated'] == len(corpus['units'])


def test_invalid_source_slice_is_detected(backend_tree):
    corpus = json.loads((backend_tree / 'testing/batch_replay/regressions.json').read_text())
    corpus['units'] = [corpus['units'][0]]
    corpus['units'][0]['references'][0]['offset_frame'] = 1
    broken = replay(corpus, backend_tree)
    assert broken['exceptions']['source_audio:ValueError:utils.batch_pipeline.source_audio.materialize'] == 1
    assert compare(broken, {'exceptions': {}, 'unit_issues': {}, 'chain_blocks': []})['regression']


def test_recorded_silence_runs_the_empty_projection_branch(backend_tree):
    corpus = json.loads((backend_tree / 'testing/batch_replay/regressions.json').read_text())
    corpus['units'] = [corpus['units'][-1]]
    corpus['units'][0].update(outcome='silence', spans=[], speech_seconds=0.0)
    result = replay(corpus, backend_tree)
    assert result['persisted'] == 1 and result['coverage']['followup_exercised'] == 1
    assert not result['exceptions'] and not result['chain_blocks']
