"""Regression coverage for the Omi-device and desktop capture pairing rule."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from routers.listen.conversations import LiveConversationController
from routers.listen import registry
from routers.listen.transcripts import TranscriptProcessor


class _Host:
    def __init__(
        self,
        *,
        existing: dict,
        source: str = 'desktop',
        onboarding_mode: bool = False,
        onboarding_admitted: bool = False,
    ) -> None:
        self.request = SimpleNamespace(uid='uid-1', source=source, onboarding_mode=onboarding_mode)
        self.client_conversation_id = 'desktop-client-id'
        self.conversation_creation_timeout = 120
        self.is_multi_channel = False
        self.onboarding_admitted = onboarding_admitted
        self.persistence = SimpleNamespace(call=self._call)
        self.existing = existing

    async def _call(self, _function, *_args, **_kwargs):
        return self.existing


async def test_client_id_session_pairs_with_live_omi_capture():
    host = _Host(
        existing={
            'id': 'omi-conversation',
            'source': 'omi',
            'finished_at': datetime.now(timezone.utc),
        }
    )
    controller = LiveConversationController(host)
    controller.create_new_in_progress_conversation = AsyncMock()

    await controller.prepare()

    controller.create_new_in_progress_conversation.assert_awaited_once_with(proposed_conversation_id='omi-conversation')


async def test_client_id_session_does_not_pair_stale_capture():
    host = _Host(
        existing={
            'id': 'stale-omi-conversation',
            'source': 'omi',
            'finished_at': datetime.now(timezone.utc) - timedelta(seconds=121),
        }
    )
    controller = LiveConversationController(host)
    controller.create_new_in_progress_conversation = AsyncMock()

    await controller.prepare()

    controller.create_new_in_progress_conversation.assert_awaited_once_with()


async def test_client_id_session_does_not_pair_web_capture():
    host = _Host(
        existing={
            'id': 'omi-conversation',
            'source': 'omi',
            'finished_at': datetime.now(timezone.utc),
        },
        source='web',
    )
    controller = LiveConversationController(host)
    controller.create_new_in_progress_conversation = AsyncMock()

    await controller.prepare()

    controller.create_new_in_progress_conversation.assert_awaited_once_with()


async def test_client_id_session_keeps_same_source_idempotency_path():
    host = _Host(
        existing={
            'id': 'omi-conversation',
            'source': 'omi',
            'finished_at': datetime.now(timezone.utc),
        },
        source='omi',
    )
    controller = LiveConversationController(host)
    controller.create_new_in_progress_conversation = AsyncMock()

    await controller.prepare()

    controller.create_new_in_progress_conversation.assert_awaited_once_with()


async def test_admitted_onboarding_session_does_not_pair_client_id_with_live_capture():
    host = _Host(
        existing={
            'id': 'omi-conversation',
            'source': 'omi',
            'finished_at': datetime.now(timezone.utc),
        },
        onboarding_mode=True,
        onboarding_admitted=True,
    )
    controller = LiveConversationController(host)
    controller.create_new_in_progress_conversation = AsyncMock()

    await controller.prepare()

    controller.create_new_in_progress_conversation.assert_awaited_once_with()


def test_transcript_writer_recognizes_pair_from_conversation_source_in_either_order():
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(
        shared_capture=False,
        request=SimpleNamespace(source='desktop'),
    )

    assert processor._is_shared_capture('omi') is True

    processor.host.request.source = 'omi'
    assert processor._is_shared_capture('desktop') is True
    assert processor._is_shared_capture('web') is False


class _RegisteredSession:
    def __init__(self, uid: str, conversation_id: str) -> None:
        self.request = SimpleNamespace(uid=uid)
        self.state = SimpleNamespace(current_conversation_id=conversation_id)
        self.shared_capture = False


def test_shared_capture_marker_reaches_active_peer_and_clears_after_last_socket():
    first = _RegisteredSession('registry-user', 'paired-conversation')
    second = _RegisteredSession('registry-user', 'paired-conversation')
    registry.register(first)
    registry.register(second)
    try:
        registry.mark_shared_capture('registry-user', 'paired-conversation')

        assert first.shared_capture is True
        assert second.shared_capture is True
        assert registry.is_shared_capture('registry-user', 'paired-conversation') is True
        registry.unregister(first)
        assert registry.has_shared_capture_peer('registry-user', 'paired-conversation') is True
    finally:
        registry.unregister(first)
        registry.unregister(second)

    assert registry.is_shared_capture('registry-user', 'paired-conversation') is False
