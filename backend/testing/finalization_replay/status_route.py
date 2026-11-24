"""Exercise the shipped FastAPI route using the replay worker's status responses."""

import json
import os
import re
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ConnectError, ReadTimeout, Response


def check_status_route(state, job_id, output):
    from routers import conversations
    from utils.conversations import workerd_finalization_status

    app = FastAPI()
    app.include_router(conversations.router)
    app.dependency_overrides[conversations.auth.get_current_user_uid] = lambda: state.uid
    with TestClient(app) as client:
        for phase, expected in (
            ('QUEUED', ('queued', False, True, 0)),
            ('TERMINAL', ('completed', True, False, 0)),
            ('UNAVAILABLE', ('completed', True, True, 0)),
            ('SLOW', ('completed', True, True, 0)),
        ):
            match = re.search(rf'^FINALIZATION_STATUS_{phase}=(.+)$', output, re.MULTILINE)
            if match is None and phase in {'QUEUED', 'TERMINAL'}:
                raise AssertionError('workerd replay status missing')
            projection = json.loads(match[1]) if match is not None else None

            def deliver(url, *, json, headers, **_):
                assert url == 'https://workerd.replay.invalid/internal/finalization/status'
                assert json == dict(owner=state.uid, conversation=state.cid, job=job_id, revision=1)
                assert headers == {'Authorization': 'Bearer replay-only'}
                if phase == 'UNAVAILABLE':
                    raise ConnectError('synthetic workerd outage')
                if phase == 'SLOW':
                    raise ReadTimeout('synthetic workerd timeout')
                return Response(200, json=projection, request=client.build_request('POST', url))

            with (
                patch.dict(os.environ, {
                    'SYNC_EPISODE_INTAKE_ORIGIN': 'https://workerd.replay.invalid',
                    'WORKER_EPISODE_INTAKE_AUDIENCE': 'fixture',
                }),
                patch.object(workerd_finalization_status, 'identity_token', lambda _: 'replay-only'),
                patch.object(workerd_finalization_status, 'httpx', SimpleNamespace(post=deliver)),
            ):
                response = client.get(f'/v1/conversations/{state.cid}/finalization')
            assert response.status_code == 200, f'public finalization status returned {response.status_code}'
            result = response.json()
            assert result['job_id'] == job_id
            assert tuple(result[field] for field in ('status', 'terminal', 'retryable', 'attempt_count')) == expected
            assert set(result) == {
                'job_id', 'status', 'terminal', 'retryable', 'attempt_count',
                'task_retry_count', 'meeting_treatment_eligible', 'terminal_outcome', 'fanout_status',
            }
