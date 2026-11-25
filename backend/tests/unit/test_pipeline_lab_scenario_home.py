"""Pipeline-lab scenario Home stage: route snapshots, on_home annotation, disagreements, the on_home check.

Pure and in-process: a tiny FastAPI app stands in for the product router (the real route runs on the emulator
in ``scenario run``). Synthetic only.
"""

import asyncio
from contextlib import ExitStack
import copy
import json
from types import SimpleNamespace

from fastapi import FastAPI, Header, Request
import pytest

from testing.pipeline_lab.scenario import home
from testing.pipeline_lab.scenario.checks import evaluate
from testing.pipeline_lab.scenario.spec import ScenarioError, parse_scenario

ID_ON = 'aaaa1111-0000-5000-8000-000000000001'
ID_OFF = 'bbbb2222-0000-5000-8000-000000000002'

BASE = {
    'name': 'tiny',
    'origins': [{'id': 'O'}],
    'recordings': [
        {'id': 'A', 'origin': 'O', 'audio': [0, 40], 'speech': [{'at': 1, 'end': 3, 'text': 'Lantern harbor.'}]}
    ],
    'finish': {'at': 38},
}


def row(handle, recordings, visible=True, **extra):
    return {
        'handle': handle,
        'recordings': recordings,
        'words': 10,
        'visible': visible,
        'hidden_reason': extra.pop('hidden_reason', None),
        'manual_end': False,
        'kind': 'conversation',
        'status': 'completed',
        'deleted': extra.pop('deleted', False),
        **extra,
    }


def fake_product_app(seen):
    """Two routes shaped like the product's; records what the recorder sent."""
    app = FastAPI()

    @app.get('/v1/conversations')
    def listed(
        request: Request,
        ownership: str = Header(None, alias='X-Omi-Home-Ownership'),
        mode: str = Header(None, alias='X-Omi-Home-Page-Mode'),
    ):
        seen.append({'query': dict(request.query_params), 'ownership': ownership, 'mode': mode})
        return [{'id': ID_ON, 'structured': {'title': 'Synthetic'}, 'v3_recording_ids': ['scn-a']}]

    @app.get('/v1/conversations/live')
    def live():
        return {'v3': True, 'conversation': None}

    return app


# ---- pure helpers -----------------------------------------------------------------------------


def test_home_handles_from_list_and_live():
    snapshot = {
        'status': 200,
        'response': [{'id': ID_ON}],
        'live': {'status': 200, 'response': {'v3': True, 'conversation': {'id': ID_OFF}}},
    }
    assert home.home_handles(snapshot) == {ID_ON[:8], ID_OFF[:8]}
    assert home.home_handles({'status': 503, 'response': {'detail': 'x'}}) is None
    assert home.home_handles({'status': 200, 'response': [], 'live': {'status': 500}}) == set()


def test_annotate_sets_on_home_or_unknown():
    rows = [row(ID_ON[:8], ['A']), row(ID_OFF[:8], ['B'], visible=False)]
    home.annotate(rows, {ID_ON[:8]})
    assert [r['on_home'] for r in rows] == [True, False]
    home.annotate(rows, None)
    assert [r['on_home'] for r in rows] == [None, None]


def test_disagreements_both_directions_and_route_only():
    rows = home.annotate(
        [
            row('agree001', ['A']),
            row('labsays1', ['B'], visible=True),  # lab visible, route did not return it
            row('routesay', ['C'], visible=False, hidden_reason='below_word_minimum'),  # route returned a hidden row
            row('deleted1', ['D'], visible=True, deleted=True),
        ],
        {'agree001', 'routesay', 'unknown9'},
    )
    found = home.disagreements('final', rows, {'agree001', 'routesay', 'unknown9'})
    by = {d['handle']: d for d in found}
    assert set(by) == {'labsays1', 'routesay', 'unknown9'}
    assert by['labsays1'] == {
        'label': 'final',
        'handle': 'labsays1',
        'recordings': ['B'],
        'lab_visible': True,
        'on_home': False,
        'hidden_reason': None,
        'status': 'completed',
    }
    assert by['routesay']['lab_visible'] is False and by['routesay']['on_home'] is True
    assert by['unknown9']['route_only'] is True
    assert json.dumps(found)  # numbers and labels only, serializable


# ---- calling a route over ASGI ------------------------------------------------------------------


def test_asgi_get_sends_the_phone_request_and_returns_the_body_unmodified():
    seen = []
    status, body = asyncio.run(
        home.asgi_get(fake_product_app(seen), home.LIST_PATH, home.LIST_QUERY, home.LIST_HEADERS)
    )
    assert status == 200
    assert body == [{'id': ID_ON, 'structured': {'title': 'Synthetic'}, 'v3_recording_ids': ['scn-a']}]
    assert seen == [
        {
            'query': {'include_discarded': 'false', 'limit': '50', 'offset': '0', 'statuses': ''},
            'ownership': '1',
            'mode': 'auto',
        }
    ]


def test_asgi_get_reports_errors_and_unparsed_bodies():
    app = FastAPI()

    @app.get('/boom')
    def boom():
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail='synthetic')

    status, body = asyncio.run(home.asgi_get(app, '/boom', {}, {}))
    assert (status, body) == (503, {'detail': 'synthetic'})
    status, body = asyncio.run(home.asgi_get(app, '/missing', {}, {}))
    assert status == 404


# ---- the recorder -------------------------------------------------------------------------------


class FakeOps:
    def __init__(self, rows, checks):
        self.rows = rows
        self.scenario = SimpleNamespace(checks=checks)
        self.calls = []

    async def _on_checkpoint(self, uid, event):
        self.calls.append(('checkpoint', event.check_index, self.snapshot(uid)))
        return {'outcome': 'ok'}

    def snapshot(self, uid):
        return copy.deepcopy(self.rows)


def recorder(tmp_path, seen, *, factory=None):
    clock = {'t': 60.0}
    rec = home.HomeRecorder(
        uid='local-dev-user',
        out_dir=tmp_path,
        offset=lambda now: now,
        now=lambda: clock['t'],
        app_factory=factory or (lambda uid: fake_product_app(seen)),
    )
    return rec, clock


def test_recorder_captures_each_checkpoint_once_and_annotates_snapshots(tmp_path):
    seen = []
    rec, clock = recorder(tmp_path, seen)
    checks = [SimpleNamespace(at=60.0), SimpleNamespace(at=60.0)]
    ops = FakeOps(
        [row(ID_ON[:8], ['A']), row(ID_OFF[:8], ['B'], visible=False, hidden_reason='below_word_minimum')], checks
    )
    with ExitStack() as stack:
        rec.install(stack, ops)
        asyncio.run(ops._on_checkpoint('local-dev-user', SimpleNamespace(check_index=0)))
        asyncio.run(ops._on_checkpoint('local-dev-user', SimpleNamespace(check_index=1)))  # same instant
        clock['t'] = 120.0
        asyncio.run(rec.final())
        final = ops.snapshot('local-dev-user')
    assert 'snapshot' not in ops.__dict__ and '_on_checkpoint' not in ops.__dict__  # unwrapped on exit
    assert [s['label'] for s in rec.snapshots] == ['checkpoint@60', 'final']
    assert len(seen) == 2
    checkpoint_rows = ops.calls[0][2]
    assert [r['on_home'] for r in checkpoint_rows] == [True, False]
    assert [r['on_home'] for r in final] == [True, False]
    assert rec.disagreements == []
    doc = json.loads((tmp_path / 'home.json').read_text())
    assert doc['schema'] == 1 and doc['route'] == 'GET /v1/conversations'
    assert doc['evidence'] == 'app/lib/providers/conversation_home_fetch.dart:115'
    assert [(s['at'], s['label'], s['status']) for s in doc['snapshots']] == [
        (60.0, 'checkpoint@60', 200),
        (120.0, 'final', 200),
    ]
    assert doc['snapshots'][-1]['response'] == [
        {'id': ID_ON, 'structured': {'title': 'Synthetic'}, 'v3_recording_ids': ['scn-a']}
    ]
    assert doc['snapshots'][-1]['live'] == {
        'route': 'GET /v1/conversations/live',
        'status': 200,
        'response': {'v3': True, 'conversation': None},
    }
    assert rec.summary() == {'route': 'GET /v1/conversations', 'snapshots': 2, 'disagreements': 0, 'errors': 0}


def test_recorder_records_a_disagreement_once(tmp_path):
    rec, _ = recorder(tmp_path, [])
    ops = FakeOps([row(ID_OFF[:8], ['B'], visible=True)], [SimpleNamespace(at=60.0)])
    with ExitStack() as stack:
        rec.install(stack, ops)
        asyncio.run(rec.final())
        ops.snapshot('u')
        ops.snapshot('u')
    assert rec.disagreements == [
        {'label': 'final', 'handle': ID_ON[:8], 'route_only': True, 'lab_visible': None, 'on_home': True},
        {
            'label': 'final',
            'handle': ID_OFF[:8],
            'recordings': ['B'],
            'lab_visible': True,
            'on_home': False,
            'hidden_reason': None,
            'status': 'completed',
        },
    ]


def test_recorder_keeps_running_when_the_route_cannot_be_built(tmp_path):
    def broken(uid):
        raise ImportError('synthetic: router import failed')

    rec, _ = recorder(tmp_path, [], factory=broken)
    ops = FakeOps([row(ID_ON[:8], ['A'])], [])
    with ExitStack() as stack:
        rec.install(stack, ops)
        asyncio.run(rec.final())
        rows = ops.snapshot('u')
    assert rows[0]['on_home'] is None
    doc = json.loads((tmp_path / 'home.json').read_text())
    assert doc['snapshots'][0]['status'] == 0
    assert 'ImportError' in doc['errors'][0]


# ---- the on_home check field --------------------------------------------------------------------


def test_on_home_is_a_check_field_and_must_be_boolean():
    raw = copy.deepcopy(BASE)
    raw['expect'] = [{'conversation_of': '@finish', 'on_home': True}]
    scenario = parse_scenario(raw)
    assert scenario.checks[0].fields == {'on_home': True}
    raw['expect'] = [{'conversation_of': '@finish', 'on_home': 'yes'}]
    with pytest.raises(ScenarioError, match='on_home'):
        parse_scenario(raw)


@pytest.mark.parametrize(
    'have, want, ok',
    [(True, True, True), (False, False, True), (True, False, False), (None, True, False), (None, False, False)],
)
def test_on_home_check_reads_the_route_annotation(have, want, ok):
    raw = copy.deepcopy(BASE)
    raw['expect'] = [{'conversation_of': 'A', 'on_home': want}]
    check = parse_scenario(raw).checks[0]
    result = evaluate(check, [row('h1', ['A'], on_home=have)], 'A')
    assert result.ok is ok
    if not ok:
        assert 'on_home' in result.detail


def test_on_home_check_misses_when_the_row_was_never_annotated():
    raw = copy.deepcopy(BASE)
    raw['expect'] = [{'conversation_of': 'A', 'on_home': True}]
    result = evaluate(parse_scenario(raw).checks[0], [row('h1', ['A'])], 'A')
    assert not result.ok and 'on_home=None' in result.detail
