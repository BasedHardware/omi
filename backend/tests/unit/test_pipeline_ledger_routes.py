"""The C2 operator routes: service-OIDC gate, aggregate-only census, explain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import pipeline_ledger_census
from utils.conversations import pipeline_ledger_metrics
from routers import pipeline_ledger as routes

BACKEND = Path(__file__).resolve().parents[2]


def _app():
    app = FastAPI()
    app.include_router(routes.router)
    return app


def _census_payload():
    return {
        'schema_version': 1,
        'generated_at': 1_800_000_000.0,
        'rows': 2,
        'by_stage': {'noted': 2},
        'stuck': {
            'by_stage': {'capturing': 0, 'sealed': 0, 'transcribed': 0, 'noted': 0},
            'affected_users': {'capturing': 0, 'sealed': 0, 'transcribed': 0, 'noted': 0},
            'oldest_age_seconds': {'capturing': 0, 'sealed': 0, 'transcribed': 0, 'noted': 0},
            'total': 0,
        },
        'new_stuck_per_hour': {'by_stage': {'capturing': 0, 'sealed': 0, 'transcribed': 0, 'noted': 0}, 'total': 0},
        'home_visible': {
            'denominator': 2,
            'real_speech': 2,
            'visible': 2,
            'share': 1.0,
            'share_lower_bound': 1.0,
            'share_upper_bound': 1.0,
            'speech_unknown': 0,
            'speech_unknown_share': 0.0,
            'home_unknown': 0,
            'basis': 'ledger_join_home_step',
        },
        'latency': {
            'clock_start': 'end_at',
            'clock_basis': 'end_at_only',
            'event': 'noted',
            'p50_seconds': 10.0,
            'p90_seconds': 20.0,
            'p50_status': 'measured',
            'p90_status': 'measured',
            'event_count': 2,
            'censored_count': 0,
            'clock_fallback_count': 0,
            'clock_unknown_count': 0,
            'basis': 'kaplan_meier',
        },
        'end_types': {
            'user_initiated': {
                'rows': 2,
                'real_speech': 2,
                'home_visible': 2,
                'share': 1.0,
                'p50_seconds': 10.0,
                'p90_seconds': 20.0,
                'p50_status': 'measured',
                'p90_status': 'measured',
                'sample_status': 'insufficient_sample',
            },
            'jev_initiated': {
                'rows': 0,
                'real_speech': 0,
                'home_visible': 0,
                'share': None,
                'p50_seconds': None,
                'p90_seconds': None,
                'p50_status': 'not_reached',
                'p90_status': 'not_reached',
                'sample_status': 'insufficient_sample',
            },
            'silence_backstop': {
                'rows': 0,
                'real_speech': 0,
                'home_visible': 0,
                'share': None,
                'p50_seconds': None,
                'p90_seconds': None,
                'p50_status': 'not_reached',
                'p90_status': 'not_reached',
                'sample_status': 'insufficient_sample',
            },
            'unknown': {
                'rows': 0,
                'real_speech': 0,
                'home_visible': 0,
                'share': None,
                'p50_seconds': None,
                'p90_seconds': None,
                'p50_status': 'not_reached',
                'p90_status': 'not_reached',
                'sample_status': 'insufficient_sample',
            },
            'terminal_rows': 2,
            'unknown_share': 0.0,
        },
        'coverage': {
            'ledger_admits': 2,
            'cohort_admits': 2,
            'excluded_admits': 0,
            'capture_creates': 2,
            'unmatched_creates': 0,
            'ratio': 1.0,
            'settle_seconds': 300,
            'basis': 'conversations_created_in_window',
            'ledger_write_failures': None,
            'ledger_disabled': None,
            'status': 'pass',
        },
        'ledger_updated_at': 1_800_000_000.0,
        'retention': {'earliest_admitted_at': 1_799_000_000.0, 'basis': 'collection_group_min'},
        'redaction': {
            'uids': False,
            'conversation_ids': False,
            'content': False,
            'titles': False,
            'transcripts': False,
        },
    }


def test_census_requires_a_service_token(monkeypatch):
    monkeypatch.delenv('PIPELINE_LEDGER_CENSUS_AUDIENCE', raising=False)
    monkeypatch.delenv('PIPELINE_LEDGER_CENSUS_INVOKER_SA', raising=False)
    response = TestClient(_app()).get('/v2/pipeline-ledger/census', params={'start': '0', 'end': '1'})
    assert response.status_code == 403


def test_census_returns_aggregates_without_ids(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    monkeypatch.setattr(pipeline_ledger_census, 'census', lambda *a, **k: _census_payload())
    monkeypatch.setattr(pipeline_ledger_metrics, 'refresh_gauges', lambda result: None)
    response = TestClient(app).get('/v2/pipeline-ledger/census', params={'start': '0', 'end': '3600'})
    assert response.status_code == 200
    body = response.json()
    assert body['rows'] == 2
    assert body['window']['seconds'] == 3600
    rendered = json.dumps(body)
    assert 'owner-secret' not in rendered
    assert 'conversation-secret' not in rendered
    assert 'A real title' not in rendered
    assert 'transcript_segments' not in rendered


def test_census_rejects_an_inverted_window(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    response = TestClient(app).get('/v2/pipeline-ledger/census', params={'start': '10', 'end': '5'})
    assert response.status_code == 422


def test_census_rejects_a_non_finite_window(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    for value in ('nan', 'inf', '-inf'):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(pipeline_ledger_census, 'census', lambda *a, **k: _census_payload())
            response = TestClient(app).get('/v2/pipeline-ledger/census', params={'start': value, 'end': '3600'})
        assert response.status_code == 422, value


def test_explain_rejects_a_slash_in_the_owner(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    monkeypatch.setattr(pipeline_ledger_census, 'explain', lambda uid, cid, **k: None)
    assert TestClient(app).get('/v2/pipeline-ledger/explain/c1', params={'uid': 'a/b'}).status_code == 422


def test_census_fails_closed_on_truncation(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None

    def truncated(*args, **kwargs):
        raise pipeline_ledger_census.pipeline_ledger.LedgerWindowTruncated('too many')

    monkeypatch.setattr(pipeline_ledger_census, 'census', truncated)
    response = TestClient(app).get('/v2/pipeline-ledger/census', params={'start': '0', 'end': '3600'})
    assert response.status_code == 503


def test_explain_returns_transitions_for_one_id(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    monkeypatch.setattr(
        pipeline_ledger_census,
        'explain',
        lambda uid, cid, **k: {
            'schema_version': 1,
            'conversation_id': cid,
            'stage': 'noted',
            'transitions': [{'stage': 'sealed', 'at': 1.0, 'reason': 'sealed'}],
            'redaction': {'uids': False, 'content': False, 'titles': False, 'transcripts': False},
        },
    )
    response = TestClient(app).get('/v2/pipeline-ledger/explain/conversation-1', params={'uid': 'owner-secret'})
    assert response.status_code == 200
    body = response.json()
    assert body['conversation_id'] == 'conversation-1'
    assert body['transitions'][0]['stage'] == 'sealed'
    assert 'owner-secret' not in json.dumps(body)


def test_explain_missing_row_is_404(monkeypatch):
    app = _app()
    app.dependency_overrides[routes.verify_census] = lambda: None
    monkeypatch.setattr(pipeline_ledger_census, 'explain', lambda uid, cid, **k: None)
    response = TestClient(app).get('/v2/pipeline-ledger/explain/missing', params={'uid': 'u'})
    assert response.status_code == 404


def test_route_policy_manifest_declares_both_routes():
    import yaml

    manifest = yaml.safe_load((BACKEND / 'route_policy_manifest.yaml').read_text(encoding='utf-8'))
    paths = {route['path'] for route in manifest['routes']}
    assert '/v2/pipeline-ledger/census' in paths
    assert '/v2/pipeline-ledger/explain/{conversation_id}' in paths
