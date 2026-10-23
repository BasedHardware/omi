"""Exercise paid recovery through the real speaker-search HTTP route, hermetically."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.users import PlanType, Subscription, SubscriptionStatus
from routers import conversations as routes
from utils.conversations import paid_lock_recovery as recovery

UID = 'paid-speaker-owner'


@contextmanager
def _context(*args, **kwargs):
    yield


def _row(cid, speaker_id, **updates):
    return {
        'id': cid,
        'created_at': datetime(2026, 10, 1, tzinfo=timezone.utc),
        'started_at': None,
        'finished_at': None,
        'deleted': False,
        'discarded': False,
        'is_locked': True,
        'structured': {'title': 'Saved meeting', 'overview': 'Preserved summary', 'emoji': '📝', 'category': 'other'},
        'transcript_segments': [
            {
                'text': 'Preserved speech',
                'start': 0,
                'end': 1,
                'speaker_id': 0,
                'is_user': speaker_id == 'user',
                'person_id': None if speaker_id == 'user' else speaker_id,
            }
        ],
        **updates,
    }


@pytest.fixture(params=['user', 'person-123'], ids=['me', 'named-person'])
def scenario(monkeypatch, request):
    speaker = request.param
    rows = {'saved': _row('saved', speaker)}
    subscription = MagicMock(return_value=Subscription(plan=PlanType.unlimited, status=SubscriptionStatus.active))
    allowance = MagicMock(return_value=SimpleNamespace(managed=True, reason='plan_unlimited'))
    signal = MagicMock()

    def persist(uid, cid, patch):
        assert uid == UID
        assert patch == {'is_locked': False}
        rows[cid].update(patch)
        return True

    write = MagicMock(side_effect=persist)
    monkeypatch.setattr(recovery.users_db, 'get_user_valid_subscription', subscription)
    monkeypatch.setattr(recovery, 'resolve_transcription_allowance', allowance)
    monkeypatch.setattr(recovery, 'fresh_cache_reads', _context)
    monkeypatch.setattr(recovery, 'external_write_fence', _context)
    monkeypatch.setattr(recovery.redis_db, 'set_credits_invalidation_signal', signal)
    monkeypatch.setattr(recovery.conversations_db, 'update_conversation', write)
    monkeypatch.setattr(routes.users_db, 'get_person', lambda uid, pid: {'id': pid} if uid == UID else None)
    monkeypatch.setattr(routes.conversations_db, 'get_conversation', lambda uid, cid, **kw: deepcopy(rows.get(cid)))
    budget = SimpleNamespace(truncated=False, observe=MagicMock())
    monkeypatch.setattr(routes.conversation_scan_db, 'conversation_scan_budget', lambda *a, **kw: budget)

    def scan(uid, **kwargs):
        assert uid == UID
        assert kwargs['budget'] is budget
        return iter(deepcopy(list(rows.values())))

    monkeypatch.setattr(routes.conversation_scan_db, 'speaker_browse_scan', scan)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    return SimpleNamespace(
        speaker=speaker,
        rows=rows,
        app=app,
        subscription=subscription,
        allowance=allowance,
        write=write,
        persist=persist,
        signal=signal,
        budget=budget,
    )


def _browse(scenario, **kwargs):
    with TestClient(scenario.app) as client:
        return client.post('/v1/conversations/search', json={'query': '', 'speaker_id': scenario.speaker, **kwargs})


def test_paid_browse_first_recovers_then_detail_and_new_client_keep_original_content(scenario):
    before = deepcopy(scenario.rows['saved'])
    response = _browse(scenario)
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['items']] == ['saved']
    assert response.json()['items'][0]['is_locked'] is False
    assert scenario.rows['saved'] == {**before, 'is_locked': False}
    scenario.write.assert_called_once_with(UID, 'saved', {'is_locked': False})
    scenario.subscription.assert_called_once_with(UID, provision=False)
    assert scenario.allowance.call_args.kwargs['byok_active'] is False
    with TestClient(scenario.app) as client:
        detail = client.get('/v1/conversations/saved')
        assert detail.status_code == 200, detail.text
        assert detail.json()['transcript_segments'][0]['text'] == 'Preserved speech'
    assert _browse(scenario).json() == response.json()
    assert scenario.write.call_count == 1
    assert scenario.subscription.call_count == 1


@pytest.mark.parametrize('reason', ['plan_within_allowance', 'usage_budget_available'])
def test_other_ordinary_paid_allowances_recover(scenario, reason):
    scenario.allowance.return_value.reason = reason
    assert [row['id'] for row in _browse(scenario).json()['items']] == ['saved']


@pytest.mark.parametrize('denial', ['free', 'inactive', 'exhausted', 'byok', 'reviewer'])
def test_unauthorized_locked_matches_stay_hidden_and_do_not_affect_pagination(scenario, denial):
    if denial == 'free':
        scenario.subscription.return_value = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active)
    elif denial == 'inactive':
        scenario.subscription.return_value.status = SubscriptionStatus.inactive
    else:
        scenario.allowance.return_value.reason = {
            'exhausted': 'plan_allowance_exhausted',
            'byok': 'byok',
            'reviewer': 'marketplace_reviewer',
        }[denial]
    response = _browse(scenario, per_page=1)
    assert response.status_code == 200, response.text
    assert response.json()['items'] == []
    assert response.json()['total_pages'] == 1
    assert scenario.rows['saved']['is_locked']
    scenario.write.assert_not_called()


@pytest.mark.parametrize('failure', ['allowance_unavailable', 'usage_invalid', 'subscription_error'])
def test_unknown_authority_is_retryable_not_an_empty_success(scenario, failure):
    if failure == 'subscription_error':
        scenario.subscription.side_effect = RuntimeError('unavailable')
    else:
        scenario.allowance.return_value.reason = failure
    response = _browse(scenario)
    assert response.status_code == 503, response.text
    assert 'items' not in response.json()
    scenario.write.assert_not_called()
    assert scenario.rows['saved']['is_locked']


@pytest.mark.parametrize('failure', [False, 'raise'])
def test_failed_persistence_returns_503_then_retry_recovers_without_content_changes(scenario, failure):
    before = deepcopy(scenario.rows['saved'])
    scenario.write.side_effect = RuntimeError('unavailable') if failure == 'raise' else lambda *a: False
    assert _browse(scenario).status_code == 503
    assert scenario.rows['saved'] == before
    scenario.write.side_effect = scenario.persist
    response = _browse(scenario)
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['items']] == ['saved']
    assert scenario.rows['saved'] == {**before, 'is_locked': False}


def test_processing_deferred_backlog_is_not_recovered_or_counted(scenario):
    scenario.rows['saved']['processing_deferred'] = True
    response = _browse(scenario, per_page=1)
    assert response.status_code == 200, response.text
    assert response.json()['items'] == []
    assert response.json()['total_pages'] == 1
    scenario.subscription.assert_not_called()
    scenario.write.assert_not_called()
    assert scenario.rows['saved']['is_locked']


def test_only_selected_page_is_persisted_not_skipped_pages_lookahead_or_unrelated_rows(scenario):
    scenario.rows.clear()
    scenario.rows['other'] = _row('other', 'someone-else')
    scenario.rows.update({f'c{i}': _row(f'c{i}', scenario.speaker) for i in range(25)})
    before = deepcopy(scenario.rows)
    response = _browse(scenario, page=2, per_page=3)
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()['items']] == ['c3', 'c4', 'c5']
    assert response.json()['total_pages'] == 3
    assert [call.args[1] for call in scenario.write.call_args_list] == ['c3', 'c4', 'c5']
    for cid in scenario.rows:
        assert scenario.rows[cid] == ({**before[cid], 'is_locked': False} if cid in {'c3', 'c4', 'c5'} else before[cid])
    assert scenario.subscription.call_count == 1
    assert scenario.allowance.call_count == 1


@pytest.mark.parametrize('kind', ['unlocked', 'unrelated'])
def test_no_matching_recoverable_lock_adds_no_entitlement_dependency(scenario, kind):
    scenario.rows['saved'] = (
        _row('saved', scenario.speaker, is_locked=False) if kind == 'unlocked' else _row('saved', 'other')
    )
    scenario.subscription.side_effect = RuntimeError('must not be read')
    response = _browse(scenario)
    assert response.status_code == 200, response.text
    assert len(response.json()['items']) == (1 if kind == 'unlocked' else 0)
    scenario.subscription.assert_not_called()
    scenario.write.assert_not_called()


def test_truncated_scan_header_is_preserved(scenario):
    scenario.budget.truncated = True
    response = _browse(scenario)
    assert response.status_code == 200, response.text
    assert response.headers['X-Omi-List-Truncated'] == 'true'
    assert response.json()['total_pages'] == 2


def test_missing_named_person_is_still_404_before_any_recovery(scenario, monkeypatch):
    monkeypatch.setattr(routes.users_db, 'get_person', lambda *args: None)
    with TestClient(scenario.app) as client:
        response = client.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'missing-person'})
    assert response.status_code == 404
    scenario.subscription.assert_not_called()
    scenario.write.assert_not_called()
