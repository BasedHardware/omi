import hashlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.serving_query_reads import list_active_desktop_prompt_snapshots
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=['desktop-prompts'])

# Remote in-app prompts: admin.omi.me authors documents in the
# `desktop_prompts` Firestore collection; every desktop client polls this
# endpoint and renders matching prompts natively — shipping a new survey,
# rating ask, or announcement needs no app release. Documents are
# admin-authored (never user input) and this route only ever READS them.
PROMPTS_COLLECTION = 'desktop_prompts'
ALLOWED_TYPES = {'stars', 'nps', 'choice', 'banner'}


class DesktopPromptSpec(BaseModel):
    id: str
    type: str
    question: str
    options: List[str] = []
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    trigger_kind: str = 'app_launch'
    trigger_count: int = 0
    max_per_day: int = 1


class DesktopPromptsResponse(BaseModel):
    prompts: List[DesktopPromptSpec]


def rollout_bucket(uid: str, prompt_id: str) -> int:
    """Stable 0-99 bucket per (user, prompt): percentage rollouts hold steady
    across polls instead of re-rolling, and a user lands in different buckets
    for different prompts."""
    digest = hashlib.sha256(f'{prompt_id}:{uid}'.encode()).hexdigest()
    return int(digest[:8], 16) % 100


def prompt_matches_audience(doc: Dict[str, Any], uid: str, channel: str, build: int) -> bool:
    audience = doc.get('audience') or {}
    if not isinstance(audience, dict):
        audience = {}
    channels = audience.get('channels') or []
    if not isinstance(channels, (list, tuple)):
        channels = []
    if channels and channel not in channels:
        return False

    raw_min = audience.get('min_build')
    try:
        min_build = int(raw_min) if raw_min is not None else 0
    except (ValueError, TypeError):
        min_build = 0

    if build and min_build and build < min_build:
        return False

    raw_rollout = audience.get('rollout_pct')
    try:
        rollout_pct = int(raw_rollout) if raw_rollout is not None else 100
    except (ValueError, TypeError):
        rollout_pct = 100

    return rollout_bucket(uid, str(doc.get('id'))) < rollout_pct


def spec_from_doc(doc: Dict[str, Any]) -> Optional[DesktopPromptSpec]:
    prompt_type = doc.get('type')
    question = doc.get('question')
    prompt_id = doc.get('id')
    if not prompt_id or prompt_type not in ALLOWED_TYPES or not question:
        return None

    trigger = doc.get('trigger') or {}
    if not isinstance(trigger, dict):
        trigger = {}
    cta = doc.get('cta') or {}
    if not isinstance(cta, dict):
        cta = {}

    raw_options = doc.get('options')
    if isinstance(raw_options, (list, tuple)):
        options = [str(o) for o in raw_options][:6]
    else:
        options = []

    try:
        trigger_count = int(trigger.get('count') or 0)
    except (ValueError, TypeError):
        trigger_count = 0

    try:
        max_per_day = int(doc.get('max_per_day') or 1)
    except (ValueError, TypeError):
        max_per_day = 1

    return DesktopPromptSpec(
        id=str(prompt_id),
        type=str(prompt_type),
        question=str(question),
        options=options,
        cta_label=str(cta.get('label')) if cta.get('label') is not None else None,
        cta_url=str(cta.get('url')) if cta.get('url') is not None else None,
        trigger_kind=str(trigger.get('kind') or 'app_launch'),
        trigger_count=trigger_count,
        max_per_day=max_per_day,
    )


@router.get('/v2/desktop/prompts', response_model=DesktopPromptsResponse)
def get_desktop_prompts(
    channel: str = 'stable',
    build: int = 0,
    uid: str = Depends(auth.get_current_user_uid),
) -> DesktopPromptsResponse:
    if build < 0:
        raise HTTPException(status_code=400, detail='build must be non-negative')
    if not channel or len(channel) > 64:
        raise HTTPException(status_code=400, detail='channel parameter is invalid')

    try:
        snapshots = list_active_desktop_prompt_snapshots()
    except Exception as e:
        logger.error(f'Failed to list active desktop prompt snapshots: {e}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to retrieve desktop prompts')

    prompts: List[DesktopPromptSpec] = []
    for snapshot in snapshots:
        try:
            doc = snapshot.to_dict() or {}
            doc.setdefault('id', snapshot.id)
            if not prompt_matches_audience(doc, uid, channel, build):
                continue
            spec = spec_from_doc(doc)
            if spec is not None:
                prompts.append(spec)
        except Exception as e:
            logger.warning(f'Skipping malformed desktop prompt snapshot {snapshot.id}: {e}')
            continue

    prompts.sort(key=lambda p: p.id)
    return DesktopPromptsResponse(prompts=prompts)
