"""Local/offline-only control plane for the named Chat-first E2E bundle."""

from fastapi import APIRouter, Depends, HTTPException, status

from config.chat_first_e2e_fixture import is_chat_first_e2e_harness_runtime
from models.chat_first_e2e import (
    ChatFirstE2EAdvanceRequest,
    ChatFirstE2EFixtureSnapshot,
    ChatFirstE2EPrepareRequest,
)
from utils.other import endpoints as auth
from utils.task_intelligence import chat_first_e2e_fixture

router = APIRouter(prefix='/v1/dev-harness/chat-first', include_in_schema=False)


def _raise_harness_error(exc: RuntimeError) -> None:
    if isinstance(exc, chat_first_e2e_fixture.ChatFirstE2EFixtureUnavailable):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found') from exc
    if isinstance(exc, chat_first_e2e_fixture.ChatFirstE2EFixtureIdentityError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found') from exc
    if isinstance(exc, chat_first_e2e_fixture.ChatFirstE2EFixtureNotPrepared):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Fixture is not prepared') from exc
    raise exc


def _require_local_harness() -> None:
    # Defense in depth: main.py does not register this router outside local or
    # offline, and a direct router inclusion in a test/server still fails here.
    if not is_chat_first_e2e_harness_runtime():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')


@router.post('/prepare', response_model=ChatFirstE2EFixtureSnapshot)
def prepare_chat_first_e2e_fixture(
    request: ChatFirstE2EPrepareRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ChatFirstE2EFixtureSnapshot:
    _require_local_harness()
    try:
        return chat_first_e2e_fixture.prepare_fixture(uid, fixture_case=request.fixture_case)
    except RuntimeError as exc:
        _raise_harness_error(exc)


@router.post('/advance-clock', response_model=ChatFirstE2EFixtureSnapshot)
def advance_chat_first_e2e_fixture_clock(
    request: ChatFirstE2EAdvanceRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> ChatFirstE2EFixtureSnapshot:
    _require_local_harness()
    try:
        return chat_first_e2e_fixture.advance_fixture_clock(uid, seconds=request.seconds)
    except RuntimeError as exc:
        _raise_harness_error(exc)


@router.get('/snapshot', response_model=ChatFirstE2EFixtureSnapshot)
def get_chat_first_e2e_fixture_snapshot(
    uid: str = Depends(auth.get_current_user_uid),
) -> ChatFirstE2EFixtureSnapshot:
    _require_local_harness()
    try:
        return chat_first_e2e_fixture.snapshot_fixture(uid)
    except RuntimeError as exc:
        _raise_harness_error(exc)
