"""Episodes API: the live occasion overlay the mobile app lists and opens.

``enabled`` in every read is the server capability. With ``EPISODES_ENABLED``
off (or outside the ramp cohort) it is false and the app keeps today's
per-conversation UI; a server that predates this router answers 404, which
the app treats the same way.

A call is admitted when the uid is in the cohort *and* the request's
``X-Omi-App-Channel`` is in ``EPISODES_CLIENT_CHANNELS`` (default ``beta``). A
store, missing or unknown channel answers ``enabled: false`` (404 for writes),
so that client keeps today's UI. Every admitted call is also the
client-capability signal: it leaves the sticky ``episodes:client_seen:{uid}``
marker (``utils/episodes/client_gate.py``, rewritten at most hourly) that listen
and the finalizer require before spending anything.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from config.episodes import APP_CHANNEL_HEADER, app_channel, client_channel_admitted, episodes_enabled_for
from models.episode import Episode, EpisodeLiveResponse, EpisodeLookupResponse, EpisodeWrapUpRequest
from utils.episodes import client_gate, metrics, service
from utils.other import endpoints as auth

router = APIRouter(tags=['episodes'])


def _admitted(uid: str, channel: Optional[str]) -> bool:
    """Cohort and client channel, then the capability marker (sync routes run off the loop)."""
    label = app_channel(channel)
    if not episodes_enabled_for(uid):
        metrics.record_client_request(label, 'not_admitted')
        return False
    if not client_channel_admitted(channel):
        metrics.record_client_request(label, 'channel_closed')
        return False
    client_gate.note_client_seen(uid)
    metrics.record_client_request(label, 'admitted')
    return True


@router.get('/v1/episodes/live', response_model=EpisodeLiveResponse, response_model_exclude_unset=True)
def get_live_episode(
    uid: str = Depends(auth.get_current_user_uid),
    channel: Optional[str] = Header(None, alias=APP_CHANNEL_HEADER),
):
    if not _admitted(uid, channel):
        return {'enabled': False, 'episode': None}
    episode = service.live_episode(uid)
    response = {
        'enabled': True,
        'episode': service.to_wire(episode),
    }
    # Without a live episode this response is the recovery-navigation answer, so the
    # recap is read fresh; alongside a live episode it comes from the poll cache.
    closed = service.last_closed_episode(uid, fresh=episode is None)
    if closed is not None:
        response['last_closed_episode'] = service.to_wire(closed)
    return response


@router.get('/v1/episodes/by-conversation/{conversation_id}', response_model=EpisodeLookupResponse)
def get_episode_for_conversation(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
    channel: Optional[str] = Header(None, alias=APP_CHANNEL_HEADER),
):
    if not _admitted(uid, channel):
        return {'enabled': False, 'episode': None}
    return {'enabled': True, 'episode': service.to_wire(service.episode_for_conversation(uid, conversation_id))}


def _require(uid: str, channel: Optional[str]) -> None:
    if not _admitted(uid, channel):
        raise HTTPException(status_code=404, detail='Episodes are not available')


@router.get('/v1/episodes/{episode_id}', response_model=Episode)
def get_episode(
    episode_id: str,
    uid: str = Depends(auth.get_current_user_uid),
    channel: Optional[str] = Header(None, alias=APP_CHANNEL_HEADER),
):
    _require(uid, channel)
    episode = service.episode_by_id(uid, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail='Episode not found')
    return service.to_wire(episode)


@router.post('/v1/episodes/{episode_id}/wrap-up', response_model=Episode)
def wrap_up_episode(
    episode_id: str,
    body: Optional[EpisodeWrapUpRequest] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'episodes:write')),
    channel: Optional[str] = Header(None, alias=APP_CHANNEL_HEADER),
):
    _require(uid, channel)
    episode = service.wrap_up(uid, episode_id, conversation_id=body.conversation_id if body else None)
    if episode is None:
        raise HTTPException(status_code=404, detail='Episode not found')
    return service.to_wire(episode)


@router.post('/v1/episodes/{episode_id}/items/{item_id}/dismiss', response_model=Episode)
def dismiss_episode_item(
    episode_id: str,
    item_id: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'episodes:write')),
    channel: Optional[str] = Header(None, alias=APP_CHANNEL_HEADER),
):
    _require(uid, channel)
    episode = service.dismiss_item(uid, episode_id, item_id)
    if episode is None:
        raise HTTPException(status_code=404, detail='Episode not found')
    return service.to_wire(episode)
