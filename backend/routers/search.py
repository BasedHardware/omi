"""Global search support routes for the mobile search screen."""

import asyncio
import logging
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends

import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
import database.folders as folders_db
import database.memories as memories_db
import database.users as users_db
from models.search import SearchOverviewFolder, SearchOverviewResponse
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


def _count_or_none(uid: str, field: str, count: Callable[[], int]) -> Optional[int]:
    """Run one count aggregation; a failure is logged and reported as None (the tile shows no number)."""
    try:
        return int(count())
    except Exception as e:
        logger.warning(f'search_overview count failed uid={uid} field={field} error={sanitize(str(e))}')
        record_fallback(
            component='firestore_read',
            from_mode='count',
            to_mode='none',
            reason='other',
            outcome='degraded',
        )
        return None


def _list_folders(uid: str) -> List[Dict[str, Any]]:
    """The user's folders in display order; empty when the read fails.

    Read-only: unlike `GET /v1/folders`, this never initializes system folders.
    """
    try:
        folders = folders_db.get_folders(uid)
    except Exception as e:
        logger.warning(f'search_overview folders read failed uid={uid} error={sanitize(str(e))}')
        record_fallback(
            component='firestore_read',
            from_mode='folders',
            to_mode='none',
            reason='other',
            outcome='degraded',
        )
        return []
    return [f for f in folders if f and f.get('id') and f.get('name')]


@router.get('/v1/search/overview', tags=['search'], response_model=SearchOverviewResponse)
async def get_search_overview(uid: str = Depends(auth.get_current_user_uid)) -> SearchOverviewResponse:
    """
    Counts for the global-search tiles shown before the user types.

    Every count is a Firestore server-side aggregation and fails independently
    (reported as null, so the tile shows no number rather than a false 0). Semantics:

    - `starred`: starred, non-discarded, non-deleted conversations (same count as
      `GET /v1/conversations/count?starred=true`).
    - `folders`: the user's folders in display order, each with its non-discarded,
      non-deleted conversation count.
    - `recaps`: stored daily summaries.
    - `memories`: approximation of the default memories list — active canonical
      memory items (Archive tier included), or the legacy collection when the
      account has no canonical items. See `count_default_visible_memories`.
    - `people`: the people (speaker profiles) collection.
    - `places`: conversations with a geolocation, discarded ones included (an
      exact non-discarded filter would need an undeclared composite index).
    """
    folders = await run_blocking(db_executor, _list_folders, uid)

    def count(field: str, fn: Callable[..., int], *args: Any, **kwargs: Any):
        return run_blocking(db_executor, _count_or_none, uid, field, partial(fn, uid, *args, **kwargs))

    starred, recaps, memories, people, places, *per_folder = await asyncio.gather(
        count('starred', conversations_db.get_conversations_count, starred=True),
        count('recaps', daily_summaries_db.get_summaries_count),
        count('memories', memories_db.count_default_visible_memories),
        count('people', users_db.count_people),
        count('places', conversations_db.count_conversations_with_geolocation),
        *(count('folder', conversations_db.get_conversations_count, folder_id=str(f['id'])) for f in folders),
    )
    return SearchOverviewResponse(
        starred=starred,
        folders=[
            SearchOverviewFolder(
                id=str(folder['id']),
                name=str(folder['name']),
                icon=str(folder.get('icon') or 'folder'),
                color=str(folder.get('color') or '#6B7280'),
                count=folder_count,
            )
            for folder, folder_count in zip(folders, per_folder)
        ],
        recaps=recaps,
        memories=memories,
        people=people,
        places=places,
    )
