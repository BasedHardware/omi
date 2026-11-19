"""Real HTTP routes and persistence with the harness's synthetic account/providers."""

from datetime import datetime, timezone


def test_date_only_reminder_stages_accepts_and_survives_rollback(
    client, fake_firestore, auth_headers, live_user, monkeypatch
):
    from models.candidate import CandidateCreate
    from utils.task_intelligence import candidate_service

    live_user.collection('task_intelligence_control').document('state').set(
        {'workflow_mode': 'read', 'account_generation': 3}
    )
    # Leave the committed delivery intent for the delivery owner. The HTTP
    # exercise must not launch executor/provider work outside this test's lifetime.
    monkeypatch.setattr(candidate_service, '_dispatch_task_integration', lambda *a, **kw: False)
    notifications = []
    monkeypatch.setattr(candidate_service, 'sync_action_item_reminder', lambda **kw: notifications.append(kw))
    source_at = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
    proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {
                'description': 'Renew the library card',
                'owner': 'user',
                'due': {'kind': 'date', 'date': '2027-01-15', 'timezone': 'Asia/Ho_Chi_Minh'},
            },
            'capture_confidence': 0.99,
            'ownership_confidence': 1,
            'source_surface': 'conversation',
            'evidence_refs': [
                {
                    'kind': 'conversation',
                    'id': 'synthetic-conversation',
                    'scope': 'canonical',
                    'transcript_segment_ids': ['synthetic-turn'],
                }
            ],
            'reminder_origin': {
                'input_revision': 'synthetic-input',
                'speaker_evidence_revision': 'synthetic-speaker',
                'source_at': source_at,
                'extracted_at': source_at,
            },
        }
    )
    headers = {**auth_headers, 'X-Account-Generation': '3', 'Idempotency-Key': 'synthetic-reminder-http'}
    staged = client.post('/v1/candidates', json=proposal.model_dump(mode='json'), headers=headers)
    assert staged.status_code == 200, staged.text
    assert staged.json()['status'] == 'pending'
    candidate_id = staged.json()['candidate_id']
    assert list(live_user.collection('action_items').stream()) == []

    accepted = client.post(f'/v1/candidates/{candidate_id}/accept', headers=headers)
    assert accepted.status_code == 200, accepted.text
    task_id = accepted.json()['task_id']
    fetched = client.get(f'/v1/action-items/{task_id}', headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    task = fetched.json()
    assert task['due']['date'] == '2027-01-15'
    assert task['due_at'] is None
    assert task['creation_receipt']['operation'] == 'create'
    assert task['creation_receipt']['actor_id'] == '123'
    assert notifications == []

    monkeypatch.setenv('ACTION_ITEM_REMINDER_REDESIGN_ENABLED', 'false')
    replay = client.post(f'/v1/candidates/{candidate_id}/accept', headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()['task_id'] == task_id
    assert replay.json()['newly_resolved'] is False
    assert len(list(live_user.collection('action_items').stream())) == 1
    assert client.get(f'/v1/action-items/{task_id}', headers=auth_headers).json()['due'] == task['due']
