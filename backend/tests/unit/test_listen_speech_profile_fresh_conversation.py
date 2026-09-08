"""A speech-profile recording session (onboarding step or Settings redo) must
start its own conversation instead of attaching to a still-open one from a
previous attempt: otherwise combine_segments() merges the new speech into that
conversation's last segment and the client replays last time's words."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.listen.conversations import LiveConversationController


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _controller(*, onboarding_mode: bool, onboarding_admitted: bool = True):
    controller = object.__new__(LiveConversationController)
    controller.host = SimpleNamespace(
        is_multi_channel=False,
        client_conversation_id=None,
        onboarding_admitted=onboarding_admitted,
        request=SimpleNamespace(uid='user-1', onboarding_mode=onboarding_mode, source='phone'),
        persistence=SimpleNamespace(call=AsyncMock(return_value=None)),
    )
    controller.create_new_in_progress_conversation = AsyncMock()  # type: ignore[method-assign]
    return controller


@pytest.mark.anyio
async def test_speech_profile_session_never_attaches_to_an_existing_conversation():
    controller = _controller(onboarding_mode=True)

    assert await controller.prepare() is None

    controller.create_new_in_progress_conversation.assert_awaited_once_with()
    controller.host.persistence.call.assert_not_awaited()


@pytest.mark.anyio
async def test_unadmitted_onboarding_claim_still_consults_the_in_progress_pointer():
    # onboarding=enabled is a client hint: without the runtime's admission the
    # fresh-conversation shortcut must not fire, or the flag alone would dodge
    # the existing-conversation behavior of an ordinary session.
    controller = _controller(onboarding_mode=True, onboarding_admitted=False)

    assert await controller.prepare() is None

    controller.host.persistence.call.assert_awaited_once()
    controller.create_new_in_progress_conversation.assert_awaited_once_with()


@pytest.mark.anyio
async def test_ordinary_session_still_consults_the_in_progress_pointer():
    controller = _controller(onboarding_mode=False)

    assert await controller.prepare() is None

    controller.host.persistence.call.assert_awaited_once()
    controller.create_new_in_progress_conversation.assert_awaited_once_with()
