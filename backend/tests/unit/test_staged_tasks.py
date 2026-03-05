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

    # --- Promote with [screen] prefix/suffix normalization ---

    def test_promote_skips_screen_prefix_duplicate(self, client):
        """Promote dedup strips [screen] prefix when comparing descriptions."""
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.promote_staged_task') as mock_promote,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_tasks_batch') as mock_batch_del,
        ):
            # Active item without [screen] prefix
            mock_active.return_value = [{'id': 'ai-1', 'description': 'Buy milk'}]
            # Staged item with [screen] prefix — should be detected as duplicate
            mock_staged.return_value = (
                [
                    {'id': 'st-1', 'description': '[screen] Buy milk', 'completed': False, 'relevance_score': 1},
                    {'id': 'st-2', 'description': 'New unique task', 'completed': False, 'relevance_score': 2},
                ],
                False,
            )
            mock_promote.return_value = {
                'id': 'ai-2',
                'description': 'New unique task',
                'completed': False,
                'created_at': now,
                'updated_at': now,
            }
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is True
            assert response.json()['promoted_task']['description'] == 'New unique task'
            # st-1 with [screen] prefix should be deleted as duplicate
            assert mock_batch_del.called
            assert 'st-1' in mock_batch_del.call_args[0][1]

    def test_promote_skips_screen_suffix_duplicate(self, client):
        """Promote dedup strips [screen] suffix when comparing descriptions."""
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.promote_staged_task') as mock_promote,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_tasks_batch') as mock_batch_del,
        ):
            # Active item with [screen] suffix
            mock_active.return_value = [{'id': 'ai-1', 'description': 'Buy milk [screen]'}]
            # Staged item without [screen] — should be detected as duplicate
            mock_staged.return_value = (
                [
                    {'id': 'st-1', 'description': 'buy milk', 'completed': False, 'relevance_score': 1},
                    {'id': 'st-2', 'description': 'Different task', 'completed': False, 'relevance_score': 2},
                ],
                False,
            )
            mock_promote.return_value = {
                'id': 'ai-2',
                'description': 'Different task',
                'completed': False,
                'created_at': now,
                'updated_at': now,
            }
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is True
            # st-1 should be deleted as duplicate
            assert mock_batch_del.called
            assert 'st-1' in mock_batch_del.call_args[0][1]

    # --- Promote boundary: 4 active should still promote ---

    def test_promote_with_4_active_succeeds(self, client):
        """Promote succeeds when exactly 4 active AI tasks (under max 5)."""
        now = datetime.now(timezone.utc)
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_active_ai_action_items') as mock_active,
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks') as mock_staged,
            patch('routers.staged_tasks.staged_tasks_db.promote_staged_task') as mock_promote,
            patch('routers.staged_tasks.staged_tasks_db.delete_staged_task'),
        ):
            mock_active.return_value = [{'id': f'ai-{i}', 'description': f'Task {i}'} for i in range(4)]
            mock_staged.return_value = (
                [{'id': 'st-1', 'description': 'New task', 'completed': False, 'relevance_score': 1}],
                False,
            )
            mock_promote.return_value = {
                'id': 'ai-5',
                'description': 'New task',
                'completed': False,
                'created_at': now,
                'updated_at': now,
            }
            response = client.post('/v1/staged-tasks/promote', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200
            assert response.json()['promoted'] is True

    # --- Cap boundary tests ---

    def test_create_description_max_length_accepted(self, client):
        """Description at exactly 2000 chars is accepted."""
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.create_staged_task') as mock_create,
        ):
            desc = 'A' * 2000
            mock_create.return_value = {
                'id': 'st-1',
                'description': desc,
                'completed': False,
            }
            response = client.post(
                '/v1/staged-tasks',
                json={'description': desc},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 200

    def test_create_description_over_max_rejected(self, client):
        """Description at 2001 chars is rejected."""
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.post(
                '/v1/staged-tasks',
                json={'description': 'A' * 2001},
                headers={'Authorization': 'Bearer test'},
            )
            assert response.status_code == 422

    def test_list_limit_1_accepted(self, client):
        """List with limit=1 is accepted."""
        with (
            patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'),
            patch('routers.staged_tasks.staged_tasks_db.get_staged_tasks', return_value=([], False)),
        ):
            response = client.get('/v1/staged-tasks?limit=1', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 200

    def test_list_limit_0_rejected(self, client):
        """List with limit=0 is rejected (min 1)."""
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.get('/v1/staged-tasks?limit=0', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 422

    def test_list_offset_negative_rejected(self, client):
        """List with offset=-1 is rejected (min 0)."""
        with patch('routers.staged_tasks.auth.get_current_user_uid', return_value='uid-1'):
            response = client.get('/v1/staged-tasks?offset=-1', headers={'Authorization': 'Bearer test'})
            assert response.status_code == 422


# --- DB Unit Tests ---


class _MockDoc:
    """Mock Firestore document snapshot."""

    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class TestStagedTasksDB:
    """Unit tests for database/staged_tasks.py functions with mocked Firestore."""

    def test_create_dedup_case_insensitive(self):
        """create_staged_task returns existing task if description matches case-insensitively."""
        import database.staged_tasks as db_mod

        existing_doc = _MockDoc('existing-1', {'description': 'Buy Milk', 'completed': False})
        mock_ref = MagicMock()
        mock_ref.stream.return_value = [existing_doc]

        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_ref
            result = db_mod.create_staged_task('uid-1', {'description': 'buy milk'})
            assert result['id'] == 'existing-1'
            assert result['description'] == 'Buy Milk'
            # Should NOT have called add (dedup returned existing)
            mock_ref.add.assert_not_called()

    def test_create_dedup_whitespace_trim(self):
        """create_staged_task trims whitespace before dedup comparison."""
        import database.staged_tasks as db_mod

        existing_doc = _MockDoc('existing-1', {'description': 'Buy Milk', 'completed': False})
        mock_ref = MagicMock()
        mock_ref.stream.return_value = [existing_doc]

        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_ref
            result = db_mod.create_staged_task('uid-1', {'description': '  buy milk  '})
            assert result['id'] == 'existing-1'
            mock_ref.add.assert_not_called()

    def test_create_dedup_skips_deleted(self):
        """create_staged_task ignores soft-deleted tasks during dedup scan."""
        import database.staged_tasks as db_mod

        deleted_doc = _MockDoc('del-1', {'description': 'Buy Milk', 'completed': False, 'deleted': True})
        mock_ref = MagicMock()
        mock_ref.stream.return_value = [deleted_doc]
        mock_ref.add.return_value = (None, MagicMock(id='new-1'))

        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_ref
            result = db_mod.create_staged_task('uid-1', {'description': 'Buy Milk'})
            # Should create new since deleted match doesn't count
            assert result['id'] == 'new-1'
            mock_ref.add.assert_called_once()

    def test_create_empty_description_raises(self):
        """create_staged_task raises ValueError for empty/whitespace description."""
        import database.staged_tasks as db_mod

        with pytest.raises(ValueError, match='description must not be empty'):
            db_mod.create_staged_task('uid-1', {'description': '   '})

    def test_get_staged_tasks_filters_completed_and_deleted(self):
        """get_staged_tasks uses completed=false filter and skips deleted client-side."""
        import database.staged_tasks as db_mod

        docs = [
            _MockDoc('t-1', {'description': 'Active', 'completed': False, 'relevance_score': 1}),
            _MockDoc('t-2', {'description': 'Deleted', 'completed': False, 'deleted': True, 'relevance_score': 2}),
            _MockDoc('t-3', {'description': 'Also active', 'completed': False, 'relevance_score': 3}),
        ]

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = docs

        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_query
            items, has_more = db_mod.get_staged_tasks('uid-1', limit=10)
            # Should have 2 items (t-2 is deleted, filtered out)
            assert len(items) == 2
            assert items[0]['id'] == 't-1'
            assert items[1]['id'] == 't-3'
            assert has_more is False

    def test_get_staged_tasks_queries_completed_false(self):
        """get_staged_tasks passes completed=false FieldFilter to Firestore."""
        import database.staged_tasks as db_mod

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with (
            patch.object(db_mod, 'db') as mock_db,
            patch.object(db_mod, 'firestore') as mock_fs,
        ):
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_query
            mock_fs.FieldFilter.return_value = 'completed_filter'
            mock_fs.Query.ASCENDING = 'ASC'
            mock_fs.Query.DESCENDING = 'DESC'

            db_mod.get_staged_tasks('uid-1')

            # Verify FieldFilter was called with completed=false
            mock_fs.FieldFilter.assert_called_once_with('completed', '==', False)
            mock_query.where.assert_called_once_with(filter='completed_filter')

    def test_daily_score_uses_due_at(self):
        """get_action_items_for_daily_score filters by due_at range."""
        import database.staged_tasks as db_mod

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = []

        with (
            patch.object(db_mod, 'db') as mock_db,
            patch.object(db_mod, 'firestore') as mock_fs,
        ):
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_query
            mock_fs.FieldFilter.side_effect = lambda field, op, val: f'{field}_{op}_{val}'

            db_mod.get_action_items_for_daily_score('uid-1', '2026-03-05T00:00:00Z', '2026-03-05T23:59:59.999Z')

            # Should have called FieldFilter with 'due_at' (not 'created_at')
            calls = mock_fs.FieldFilter.call_args_list
            fields_used = [c[0][0] for c in calls]
            assert 'due_at' in fields_used
            assert 'created_at' not in fields_used

    def test_weekly_score_uses_created_at(self):
        """get_action_items_for_weekly_score filters by created_at range (not due_at)."""
        import database.staged_tasks as db_mod

        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = []

        with (
            patch.object(db_mod, 'db') as mock_db,
            patch.object(db_mod, 'firestore') as mock_fs,
        ):
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_query
            mock_fs.FieldFilter.side_effect = lambda field, op, val: f'{field}_{op}_{val}'

            db_mod.get_action_items_for_weekly_score('uid-1', '2026-02-26T00:00:00Z', '2026-03-05T23:59:59.999Z')

            # Should have called FieldFilter with 'created_at' (not 'due_at')
            calls = mock_fs.FieldFilter.call_args_list
            fields_used = [c[0][0] for c in calls]
            assert 'created_at' in fields_used
            assert 'due_at' not in fields_used

    def test_overall_score_counts_all_non_deleted(self):
        """get_action_items_for_overall_score scans all docs, skips deleted."""
        import database.staged_tasks as db_mod

        docs = [
            _MockDoc('a-1', {'completed': True}),
            _MockDoc('a-2', {'completed': False}),
            _MockDoc('a-3', {'completed': True, 'deleted': True}),  # Should be skipped
            _MockDoc('a-4', {'completed': False}),
        ]

        mock_ref = MagicMock()
        mock_ref.stream.return_value = docs

        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value = mock_ref
            completed, total = db_mod.get_action_items_for_overall_score('uid-1')
            assert completed == 1  # Only a-1 (a-3 is deleted)
            assert total == 3  # a-1, a-2, a-4 (a-3 is deleted)

    def test_delete_is_idempotent(self):
        """delete_staged_task calls Firestore delete without checking existence."""
        import database.staged_tasks as db_mod

        mock_doc_ref = MagicMock()
        with patch.object(db_mod, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            # Should not raise even if doc doesn't exist
            db_mod.delete_staged_task('uid-1', 'nonexistent-id')
            mock_doc_ref.delete.assert_called_once()
