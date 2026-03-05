"""Tests for desktop staged tasks + daily scores endpoints."""

import sys
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.firestore',
    'firebase_admin.messaging',
    'google.cloud',
    'google.cloud.exceptions',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
    'google.cloud.firestore_v1.query',
    'google.cloud.storage',
    'google.cloud.storage.blob',
    'google.cloud.storage.bucket',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.oauth2',
    'google.oauth2.service_account',
    'pinecone',
    'typesense',
]:
    sys.modules.setdefault(mod_name, MagicMock())

from routers.staged_tasks import (
    CreateStagedTaskRequest,
    StagedTaskResponse,
    StagedTasksListResponse,
    BatchUpdateScoresRequest,
    ScoreUpdate,
    PromoteResponse,
    DailyScoreResponse,
    ScoresResponse,
    ScoreData,
    StatusResponse,
    router,
)

# --- Model Tests ---


class TestStagedTaskModels:
    def test_create_request_required_fields(self):
        req = CreateStagedTaskRequest(description='Buy groceries')
        assert req.description == 'Buy groceries'
        assert req.source is None
        assert req.relevance_score is None

    def test_create_request_all_fields(self):
        req = CreateStagedTaskRequest(
            description='Ship feature',
            source='screenshot',
            priority='high',
            metadata='{"app": "Safari"}',
            category='work',
            relevance_score=3,
        )
        assert req.priority == 'high'
        assert req.relevance_score == 3

    def test_create_request_blank_description_rejected(self):
        with pytest.raises(Exception):
            CreateStagedTaskRequest(description='   ')

    def test_batch_scores_request(self):
        req = BatchUpdateScoresRequest(scores=[ScoreUpdate(id='t1', relevance_score=5)])
        assert len(req.scores) == 1

    def test_batch_scores_empty_rejected(self):
        with pytest.raises(Exception):
            BatchUpdateScoresRequest(scores=[])

    def test_promote_response(self):
        resp = PromoteResponse(promoted=True, promoted_task=StagedTaskResponse(id='t1', description='Task'))
        assert resp.promoted is True
        assert resp.promoted_task.id == 't1'

    def test_daily_score_response(self):
        resp = DailyScoreResponse(score=75.0, completed_tasks=3, total_tasks=4, date='2026-03-05')
        assert resp.score == 75.0

    def test_scores_response(self):
        data = ScoreData(score=50.0, completed_tasks=1, total_tasks=2)
        resp = ScoresResponse(daily=data, weekly=data, overall=data, default_tab='daily', date='2026-03-05')
        assert resp.default_tab == 'daily'


# --- Endpoint Tests ---


class TestStagedTaskEndpoints:
    def _make_app(self):
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        return TestClient(self._make_app())

    def test_create_staged_task(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.create_staged_task') as mock_create,
        ):
            mock_create.return_value = {
                'id': 'st-1',
                'description': 'Buy milk',
                'completed': False,
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc),
            }
            response = client.post(
                '/v1/staged-tasks',
                json={'description': 'Buy milk', 'source': 'screenshot', 'relevance_score': 5},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert response.json()['id'] == 'st-1'
            assert response.json()['description'] == 'Buy milk'

    def test_create_staged_task_blank_desc_422(self, client):
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.post(
                '/v1/staged-tasks',
                json={'description': '   '},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_list_staged_tasks(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_get,
        ):
            mock_get.return_value = (
                [
                    {'id': 'st-1', 'description': 'Task 1', 'completed': False, 'relevance_score': 1},
                    {'id': 'st-2', 'description': 'Task 2', 'completed': False, 'relevance_score': 3},
                ],
                False,
            )
            response = client.get('/v1/staged-tasks', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert len(data['items']) == 2
            assert data['has_more'] is False

    def test_list_staged_tasks_with_pagination(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_get,
        ):
            mock_get.return_value = ([], True)
            response = client.get(
                '/v1/staged-tasks?limit=10&offset=20',
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert mock_get.called
            assert mock_get.call_args[1] == {'limit': 10, 'offset': 20}

    def test_list_staged_tasks_limit_over_max_422(self, client):
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.get(
                '/v1/staged-tasks?limit=501',
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_delete_staged_task(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task') as mock_del,
        ):
            response = client.delete('/v1/staged-tasks/st-1', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'
            assert mock_del.called

    def test_delete_staged_task_idempotent(self, client):
        """Delete returns 200 even for non-existent task (matches Rust behavior)."""
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
        ):
            response = client.delete('/v1/staged-tasks/missing', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'

    def test_batch_update_scores(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.batch_update_scores') as mock_batch,
        ):
            response = client.patch(
                '/v1/staged-tasks/batch-scores',
                json={'scores': [{'id': 'st-1', 'relevance_score': 10}, {'id': 'st-2', 'relevance_score': 3}]},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert mock_batch.called
            assert len(mock_batch.call_args[0][1]) == 2

    def test_batch_update_scores_empty_422(self, client):
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.patch(
                '/v1/staged-tasks/batch-scores',
                json={'scores': []},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_promote_success(self, client):
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items', return_value=[]),
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.promote_staged_task') as mock_promote,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
        ):
            mock_staged.return_value = (
                [
                    {'id': 'st-1', 'description': 'Top task', 'completed': False, 'relevance_score': 1},
                ],
                False,
            )
            mock_promote.return_value = {
                'id': 'ai-1',
                'description': 'Top task',
                'completed': False,
                'created_at': now,
                'updated_at': now,
                'from_staged': True,
            }
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert data['promoted'] is True
            assert data['promoted_task']['id'] == 'ai-1'

    def test_promote_max_active_returns_false(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
        ):
            mock_active.return_value = [{'id': f'ai-{i}', 'description': f'Task {i}'} for i in range(5)]
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert data['promoted'] is False
            assert 'max 5' in data['reason']

    def test_promote_no_staged_tasks(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items', return_value=[]),
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks', return_value=([], False)),
        ):
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is False
            assert 'No staged tasks' in response.json()['reason']

    def test_promote_skips_duplicates(self, client):
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.promote_staged_task') as mock_promote,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_tasks_batch') as mock_batch_del,
        ):
            mock_active.return_value = [{'id': 'ai-1', 'description': 'Buy groceries'}]
            mock_staged.return_value = (
                [
                    {'id': 'st-1', 'description': 'buy groceries', 'completed': False, 'relevance_score': 1},
                    {'id': 'st-2', 'description': 'Ship feature', 'completed': False, 'relevance_score': 2},
                ],
                False,
            )
            mock_promote.return_value = {
                'id': 'ai-2',
                'description': 'Ship feature',
                'completed': False,
                'created_at': now,
                'updated_at': now,
            }
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is True
            assert response.json()['promoted_task']['description'] == 'Ship feature'
            # st-1 should be batch-deleted as duplicate
            assert mock_batch_del.called
            assert mock_batch_del.call_args[0][1] == ['st-1']

    def test_promote_all_duplicates(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_tasks_batch'),
        ):
            mock_active.return_value = [{'id': 'ai-1', 'description': 'Task A'}]
            mock_staged.return_value = (
                [
                    {'id': 'st-1', 'description': 'task a', 'completed': False, 'relevance_score': 1},
                ],
                False,
            )
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is False
            assert 'duplicates' in response.json()['reason']


class TestDailyScoreEndpoints:
    def _make_app(self):
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        return TestClient(self._make_app())

    def test_daily_score_today(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(3, 4)),
        ):
            response = client.get('/v1/daily-score', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert data['score'] == 75.0
            assert data['completed_tasks'] == 3
            assert data['total_tasks'] == 4

    def test_daily_score_specific_date(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(0, 0)),
        ):
            response = client.get('/v1/daily-score?date=2026-01-15', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['date'] == '2026-01-15'
            assert response.json()['score'] == 0.0

    def test_daily_score_invalid_date_400(self, client):
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.get('/v1/daily-score?date=not-a-date', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 400

    def test_scores_all_three(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(2, 4)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_weekly_score', return_value=(10, 20)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_overall_score', return_value=(50, 100)),
        ):
            response = client.get('/v1/scores', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert data['daily']['score'] == 50.0
            assert data['weekly']['score'] == 50.0
            assert data['overall']['score'] == 50.0

    def test_scores_default_tab_daily_when_highest(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(4, 4)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_weekly_score', return_value=(5, 10)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_overall_score', return_value=(10, 30)),
        ):
            response = client.get('/v1/scores', headers={'Authorization': 'Bearer test'})
            assert response.json()['default_tab'] == 'daily'

    def test_scores_default_tab_weekly_when_no_daily(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(0, 0)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_weekly_score', return_value=(5, 10)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_overall_score', return_value=(10, 30)),
        ):
            response = client.get('/v1/scores', headers={'Authorization': 'Bearer test'})
            assert response.json()['default_tab'] == 'weekly'

    def test_scores_invalid_date_400(self, client):
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.get('/v1/scores?date=bad', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 400

    def test_scores_no_tasks_zero(self, client):
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(0, 0)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_weekly_score', return_value=(0, 0)),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_overall_score', return_value=(0, 0)),
        ):
            response = client.get('/v1/scores', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            data = response.json()
            assert data['daily']['score'] == 0.0
            assert data['weekly']['score'] == 0.0
            assert data['overall']['score'] == 0.0

    def test_create_dedup_returns_existing(self, client):
        """Create returns existing task if description matches (case-insensitive)."""
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.create_staged_task') as mock_create,
        ):
            # Simulate dedup returning existing task
            mock_create.return_value = {
                'id': 'existing-1',
                'description': 'Buy milk',
                'completed': False,
                'created_at': now,
                'updated_at': now,
            }
            response = client.post(
                '/v1/staged-tasks',
                json={'description': 'buy milk'},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200
            assert response.json()['id'] == 'existing-1'

    def test_weekly_score_uses_created_at(self, client):
        """Weekly score filters by created_at range, not due_at."""
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_daily_score', return_value=(1, 2)),
            patch(
                'routers.staged_tasks.staged_tasks_db.get_action_items_for_weekly_score', return_value=(7, 14)
            ) as mock_weekly,
            patch('routers.staged_tasks.staged_tasks_db.get_action_items_for_overall_score', return_value=(20, 40)),
        ):
            response = client.get('/v1/scores?date=2026-03-05', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert mock_weekly.called
            # Weekly should use a 7-day window ending today
            week_start_arg = mock_weekly.call_args[0][1]
            assert '2026-02-26' in week_start_arg
