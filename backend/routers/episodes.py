"""Episodes API: the live occasion overlay the mobile app lists and opens.

``enabled`` in every read is the server capability. With ``EPISODES_ENABLED``
off (or outside the ramp cohort) it is false and the app keeps today's
per-conversation UI; a server that predates this router answers 404, which
the app treats the same way.

Every call by an admitted uid is also the client-capability signal: it leaves
the sticky ``episodes:client_seen:{uid}`` marker (``utils/episodes/client_gate.py``,
rewritten at most hourly) that listen and the finalizer require before spending
anything. The API stays available to every admitted uid, because it is what
sets the marker.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config.episodes import episodes_enabled_for
from models.episode import Episode, EpisodeLiveResponse, EpisodeLookupResponse, EpisodeWrapUpRequest
from utils.episodes import client_gate, service
from utils.other import endpoints as auth

router = APIRouter(tags=['episodes'])


def _admitted(uid: str) -> bool:
    """Admission, and the capability marker for an admitted caller (sync routes run off the loop)."""
    if not episodes_enabled_for(uid):
        return False
    client_gate.note_client_seen(uid)
    return True


@router.get('/v1/episodes/live', response_model=EpisodeLiveResponse)
def get_live_episode(uid: str = Depends(auth.get_current_user_uid)):
    if not _admitted(uid):
        return {'enabled': False, 'episode': None}
    return {'enabled': True, 'episode': service.to_wire(service.live_episode(uid))}


@router.get('/v1/episodes/by-conversation/{conversation_id}', response_model=EpisodeLookupResponse)
def get_episode_for_conversation(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    if not _admitted(uid):
        return {'enabled': False, 'episode': None}
    return {'enabled': True, 'episode': service.to_wire(service.episode_for_conversation(uid, conversation_id))}


def _require(uid: str) -> None:
    if not _admitted(uid):
        raise HTTPException(status_code=404, detail='Episodes are not available')


@router.post('/v1/episodes/{episode_id}/wrap-up', response_model=Episode)
def wrap_up_episode(
    episode_id: str,
    body: Optional[EpisodeWrapUpRequest] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'episodes:write')),
):
    _require(uid)
    episode = service.wrap_up(uid, episode_id, conversation_id=body.conversation_id if body else None)
    if episode is None:
        raise HTTPException(status_code=404, detail='Episode not found')
    return service.to_wire(episode)


@router.post('/v1/episodes/{episode_id}/items/{item_id}/dismiss', response_model=Episode)
def dismiss_episode_item(
    episode_id: str,
    item_id: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'episodes:write')),
):
    _require(uid)
    episode = service.dismiss_item(uid, episode_id, item_id)
    if episode is None:
        raise HTTPException(status_code=404, detail='Episode not found')
    return service.to_wire(episode)
