"""PFS-F2: a client-id create that loses the idempotent race snapshots the stored row.

Another writer can create the client's conversation id between the probe and
the create. ``create_in_progress_conversation`` then returns False. Pinning
``batch_record_capture`` to None held a batch-owned recording ineligible for the
live-STT retirement cohort for the whole socket.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as conversations_db
from database import redis_db
from routers.listen.conversations import LiveConversationController
from utils.conversations import lifecycle as lifecycle_service

STORED = {
    'id': 'client-conversation',
    'status': 'in_progress',
    'record_lane_owner': 'batch_live_v1',
    'private_cloud_sync_enabled': False,
    'uses_custom_stt': False,
    'data_protection_level': 'standard',
    'language': 'en',
    'transcript_segments': [{'text': 'synthetic'}],
}


class _Stop(Exception):
    pass


def _controller(*, created: bool):
    reads: list[str] = []
    creates: list[dict] = []

    async def call(function, *args, **kwargs):
        if function is lifecycle_service.open_live_recording_session:
            return {'requires_rollover': False, 'conversation_id': args[2]}
        if function is conversations_db.get_conversation:
            reads.append(args[1])
            # The probe finds nothing; the row exists by the time the create runs.
            return None if len(reads) == 1 else dict(STORED)
        if function is lifecycle_service.create_in_progress_conversation:
            creates.append(kwargs)
            return created
        if function is redis_db.set_in_progress_conversation_id:
            raise _Stop()
        return None

    controller = LiveConversationController.__new__(LiveConversationController)
    controller.clock = lambda: datetime(2026, 10, 20, tzinfo=timezone.utc)
    controller.host = SimpleNamespace(
        request=SimpleNamespace(
            uid='uid',
            source='omi',
            conversation_role=None,
            call_id=None,
            geolocation=None,
            onboarding_mode=False,
            screen_evidence_pass=False,
        ),
        client_conversation_id='client-conversation',
        recording_session_id=None,
        recording_session_ids_by_conversation={},
        persistence=SimpleNamespace(call=call),
        client_device_context=SimpleNamespace(client_device_id='phone_a1b2c3d4', platform='ios'),
        language='en',
        private_cloud_sync_enabled=False,
        use_custom_stt=False,
        is_multi_channel=False,
        onboarding_admitted=False,
        batch_record_capture='unset',
    )
    return controller, reads, creates


def _run(controller):
    with pytest.raises(_Stop):
        asyncio.run(controller.create_new_in_progress_conversation())


def test_idempotent_create_false_snapshots_the_stored_row(monkeypatch):
    monkeypatch.setattr('routers.listen.conversations.sync_lineage_resolve_enabled', lambda: False, raising=False)
    controller, reads, creates = _controller(created=False)
    _run(controller)

    assert creates == [{'idempotent': True}]
    assert reads == ['client-conversation', 'client-conversation']
    capture = controller.host.batch_record_capture
    assert capture['id'] == 'client-conversation'
    assert capture['record_lane_owner'] == 'batch_live_v1'
    assert 'transcript_segments' not in capture


def test_fresh_create_snapshots_the_payload_without_a_second_read(monkeypatch):
    monkeypatch.setattr('routers.listen.conversations.sync_lineage_resolve_enabled', lambda: False, raising=False)
    controller, reads, _creates = _controller(created=True)
    _run(controller)

    assert reads == ['client-conversation']
    assert controller.host.batch_record_capture['id'] == 'client-conversation'
