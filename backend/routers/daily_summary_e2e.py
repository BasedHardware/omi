"""Local/offline-only daily-summary fixture for the desktop memory-review flow.

The desktop's "Things I learned today" review rows are rendered only from a
daily summary's ``memories_learned``, and the only producer of that record is
the scheduled nightly job: it needs a day of conversations and a model call, so
a hermetic bundle can never reach one. That left the whole review card —
projection, row state machine, and the three mutations — unreachable from an
E2E flow, which is why ``memory-review.yaml`` did not exist.

This writes the record the job would have written, and nothing else. It does
**not** create memories: the flow creates those through the production
``POST /v3/memories`` so the ids it hands over address real rows that
``/v3/memories/{id}/review`` and ``PATCH /v3/memories/{id}`` really mutate. A
fixture that minted its own memory rows would prove the card can render and
prove nothing about whether a vote lands.

Local/offline only, by the same stage boundary as the Chat-first E2E fixture:
the router is not registered elsewhere, and the handler repeats the check.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from config.chat_first_e2e_fixture import is_chat_first_e2e_harness_runtime
from database import daily_summaries as daily_summaries_db
from models.daily_summary_payload import LearnedMemoryRef
from utils.other import endpoints as auth

router = APIRouter(prefix='/v1/dev-harness/daily-summary', include_in_schema=False)

# The card renders at most three rows; the fixture accepts a few more so a flow
# can prove the bound rather than assume it.
MAX_FIXTURE_MEMORIES = 8
MAX_FIXTURE_CONTENT_CHARS = 400


class DailySummaryFixtureMemory(BaseModel):
    memory_id: str
    content: str
    category: str = ''


class DailySummaryFixtureRequest(BaseModel):
    memories: List[DailySummaryFixtureMemory] = Field(default_factory=list)
    date: Optional[str] = None
    headline: str = 'Your day in review'
    overview: str = 'A hermetic fixture day for the memory review card.'


class DailySummaryFixtureResponse(BaseModel):
    status: str
    summary_id: str
    date: str
    memories_learned: int


def _require_local_harness() -> None:
    # Defense in depth: main.py does not register this router outside local or
    # offline, and a direct router inclusion in a test/server still fails here.
    if not is_chat_first_e2e_harness_runtime():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')


def _resolved_date(raw: Optional[str]) -> str:
    if raw is None:
        return datetime.now(timezone.utc).date().isoformat()
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date().isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail='Invalid date format. Use YYYY-MM-DD') from None


def _learned_refs(memories: List[DailySummaryFixtureMemory]) -> List[LearnedMemoryRef]:
    """Type the entries through the model production writes, so the two cannot drift.

    A blank id or blank content is rejected rather than trimmed away: the flow
    asserts row identity, and a row whose ✓ / ✗ / Fix addresses no memory would
    make the fixture look richer than it is.
    """
    refs: List[LearnedMemoryRef] = []
    for memory in memories:
        memory_id = memory.memory_id.strip()
        content = memory.content.strip()
        if not memory_id or not content:
            raise HTTPException(status_code=400, detail='Every fixture memory needs a memory_id and content')
        refs.append(
            LearnedMemoryRef(
                memory_id=memory_id,
                content=content[:MAX_FIXTURE_CONTENT_CHARS],
                category=memory.category.strip(),
                captured_at=datetime.now(timezone.utc),
            )
        )
    return refs


@router.post('/seed', response_model=DailySummaryFixtureResponse)
def seed_daily_summary_fixture(
    request: DailySummaryFixtureRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> DailySummaryFixtureResponse:
    _require_local_harness()
    if not request.memories:
        raise HTTPException(status_code=400, detail='At least one fixture memory is required')
    if len(request.memories) > MAX_FIXTURE_MEMORIES:
        raise HTTPException(status_code=400, detail=f'At most {MAX_FIXTURE_MEMORIES} fixture memories')

    date_str = _resolved_date(request.date)
    refs = _learned_refs(request.memories)
    # Deterministic id keyed to the day, so re-running the flow overwrites the
    # record it wrote last time instead of leaving two summaries competing for
    # the newest-first read the desktop makes.
    summary_id = f'dev-harness-daily-summary-{date_str}'
    summary_data = {
        'id': summary_id,
        'date': date_str,
        'created_at': datetime.now(timezone.utc),
        'headline': request.headline,
        'overview': request.overview,
        'day_emoji': '🧪',
        'highlights': [],
        'action_items': [],
        'memories_learned': [ref.model_dump(mode='json') for ref in refs],
    }
    daily_summaries_db.create_daily_summary(uid, summary_data)
    return DailySummaryFixtureResponse(
        status='ok',
        summary_id=summary_id,
        date=date_str,
        memories_learned=len(refs),
    )
