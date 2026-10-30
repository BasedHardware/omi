"""Record-path trace replay: content-free session traces through the real pusher seal path.

Each testing/record_traces/traces/*.json trace seeds a completed conversation row, replays one or more
websocket sessions (103 conversation, 101 audio of N seconds, 104 finalize) with a scripted upload outcome,
then asserts the end state batch admission depends on: sealed, sticky upload failure, open producer tokens,
and whether require_record_audio_barrier would admit the row. Batch shadow re-runs recognition only and
never exercises this path; both 10-29/30 live stops were here. Add a trace for every record-path incident.
Archive listing and tail durability are proved at admission against storage and are out of scope here.
"""

import json
from pathlib import Path

import pytest

from config.record_audio import require_record_audio_barrier
import routers.pusher as pusher
from tests.unit.test_pusher_audio_timeline import env, FakeWebSocket, _audio, _conversation, _run, RATE  # noqa: F401
from tests.unit.test_record_audio_seal import PATH, _finalize, records  # noqa: F401

TRACES = Path(__file__).resolve().parents[2] / 'testing' / 'record_traces' / 'traces'
SCHEMA = 'record-trace/1'
EXPECT = ('sealed', 'upload_failed', 'open_tokens', 'admissible')


def _load():
    traces = []
    for path in sorted(TRACES.glob('*.json')):
        trace = json.loads(path.read_text())
        assert trace['schema'] == SCHEMA, path.name
        assert trace['name'] == path.stem, path.name
        assert set(trace['expect']) == set(EXPECT), path.name
        audio = any(isinstance(f, dict) for session in trace['sessions'] for f in session['frames'])
        # The durable outbox commits audio to storage this runner does not fake, so an audio trace there
        # could pass without exercising custody (Luna #24106 r1). Finalize-only sessions upload nothing.
        assert not (audio and True in trace['durable']), f'{path.name}: durable audio replay needs an outbox fake'
        for durable in trace['durable']:
            traces.append(pytest.param(trace, durable, id=f'{trace["name"]}[durable={durable}]'))
    return traces


def _frames(session):
    frames, ts = [], 100.0
    for frame in session['frames']:
        if frame == 'conversation':
            frames.append(_conversation(PATH[-1]))
        elif frame == 'finalize':
            frames.append(_finalize())
        elif isinstance(frame, dict) and set(frame) == {'audio_seconds'}:
            seconds = int(frame['audio_seconds'])
            assert 1 <= seconds <= 30
            frames.append(_audio(ts, b'\x01\x00' * RATE * seconds))
            ts += seconds
        else:
            raise AssertionError(f'unknown trace frame {frame!r}')
    return frames


def test_corpus_is_content_free_and_well_formed():
    paths = sorted(TRACES.glob('*.json'))
    assert paths
    allowed = {'schema', 'name', 'source', 'row', 'durable', 'sessions', 'expect', 'known_gap'}
    for path in paths:
        trace = json.loads(path.read_text())
        assert set(trace) <= allowed, path.name
        assert set(trace['row']) <= {'record_lane_owner', 'record_upload_sessions'}, path.name
        for session in trace['sessions']:
            assert session['upload'] in {'ok', 'fail'}, path.name
            _frames(session)


@pytest.mark.parametrize('trace,durable', _load())
async def test_record_trace(trace, durable, records, env, monkeypatch):  # noqa: F811
    records.rows[PATH].update(trace['row'])
    upload = pusher.upload_audio_chunks_batch  # the env fixture's recording fake

    def failed(*args, **kwargs):
        raise ValueError('synthetic upload failure')

    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', str(durable).lower())
    for session in trace['sessions']:
        monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', failed if session['upload'] == 'fail' else upload)
        await _run(FakeWebSocket(_frames(session)))
    row = records.rows[PATH]
    try:
        require_record_audio_barrier(row)
        admissible = True
    except ValueError:
        admissible = False
    got = dict(
        sealed=bool(row.get('record_audio_closed')),
        upload_failed=bool(row.get('record_upload_failed')),
        open_tokens=len(row.get('record_upload_sessions') or {}),
        admissible=admissible,
    )
    assert got == trace['expect'], trace.get('known_gap') or trace['source']
