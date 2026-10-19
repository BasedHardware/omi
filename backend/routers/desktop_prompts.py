import hashlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database.serving_query_reads import list_active_desktop_prompt_snapshots
from utils.log_sanitizer import sanitize
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


def _coerce_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def rollout_bucket(uid: str, prompt_id: str) -> int:
    """Stable 0-99 bucket per (user, prompt): percentage rollouts hold steady
    across polls instead of re-rolling, and a user lands in different buckets
    for different prompts."""
    digest = hashlib.sha256(f'{prompt_id}:{uid}'.encode()).hexdigest()
    return int(digest[:8], 16) % 100


def prompt_matches_audience(doc: Dict[str, Any], uid: str, channel: str, build: int) -> bool:
    if not isinstance(doc, dict):
        return False
    raw_audience = doc.get('audience')
    if raw_audience is None:
        audience: Dict[str, Any] = {}
    elif isinstance(raw_audience, dict):
        audience = raw_audience
    else:
        return False

    raw_channels = audience.get('channels')
    if raw_channels is not None:
        if not isinstance(raw_channels, (list, tuple, set)):
            return False
        channels = [c.strip() for c in raw_channels if isinstance(c, str) and c.strip()]
        if raw_channels and not channels:
            return False
        if channels and channel not in channels:
            return False

    raw_min_build = audience.get('min_build')
    if raw_min_build is not None:
        min_build = _coerce_int(raw_min_build)
        if min_build is None or min_build < 0:
            return False
        if build and min_build and build < min_build:
            return False

    raw_rollout_pct = audience.get('rollout_pct')
    if raw_rollout_pct is None:
        rollout_pct = 100
    else:
        parsed_pct = _coerce_int(raw_rollout_pct)
        if parsed_pct is None:
            return False
        rollout_pct = max(0, min(100, parsed_pct))

    prompt_id = doc.get('id')
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        return False
    return rollout_bucket(uid, prompt_id.strip()) < rollout_pct


def spec_from_doc(doc: Dict[str, Any]) -> Optional[DesktopPromptSpec]:
    if not isinstance(doc, dict):
        return None
    prompt_type = doc.get('type')
    question = doc.get('question')
    prompt_id = doc.get('id')
    if (
        not isinstance(prompt_id, str)
        or not prompt_id.strip()
        or not isinstance(prompt_type, str)
        or prompt_type not in ALLOWED_TYPES
        or not isinstance(question, str)
        or not question.strip()
    ):
        return None

    raw_trigger = doc.get('trigger')
    trigger = raw_trigger if isinstance(raw_trigger, dict) else {}
    raw_cta = doc.get('cta')
    cta = raw_cta if isinstance(raw_cta, dict) else {}

    raw_options = doc.get('options')
    if isinstance(raw_options, (list, tuple)):
        options = [str(o).strip() for o in raw_options if o is not None and not isinstance(o, bool) and str(o).strip()][
            :6
        ]
    else:
        options = []

    raw_label = cta.get('label')
    cta_label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else None
    raw_url = cta.get('url')
    cta_url = raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None

    raw_kind = trigger.get('kind')
    trigger_kind = raw_kind.strip() if isinstance(raw_kind, str) and raw_kind.strip() else 'app_launch'

    parsed_count = _coerce_int(trigger.get('count'), default=0)
    trigger_count = max(0, parsed_count if parsed_count is not None else 0)

    parsed_max = _coerce_int(doc.get('max_per_day'), default=1)
    max_per_day = max(0, parsed_max if parsed_max is not None else 1)

    return DesktopPromptSpec(
        id=prompt_id.strip(),
        type=prompt_type,
        question=question.strip(),
        options=options,
        cta_label=cta_label,
        cta_url=cta_url,
        trigger_kind=trigger_kind,
        trigger_count=trigger_count,
        max_per_day=max_per_day,
    )


@router.get('/v2/desktop/prompts', response_model=DesktopPromptsResponse)
def get_desktop_prompts(
    channel: str = 'stable',
    build: int = 0,
    uid: str = Depends(auth.get_current_user_uid),
) -> DesktopPromptsResponse:
    try:
        snapshots = list_active_desktop_prompt_snapshots()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'desktop_prompts list failed uid={uid}: {sanitize(str(e))}', exc_info=True)
        raise HTTPException(status_code=500, detail='Failed to load desktop prompts')

    prompts: List[DesktopPromptSpec] = []
    for snapshot in snapshots:
        try:
            raw_doc = snapshot.to_dict()
            if not isinstance(raw_doc, dict):
                continue
            doc = dict(raw_doc)
            if not isinstance(doc.get('id'), str) or not doc['id'].strip():
                doc['id'] = getattr(snapshot, 'id', None)
            if not prompt_matches_audience(doc, uid, channel, build):
                continue
            spec = spec_from_doc(doc)
            if spec is not None:
                prompts.append(spec)
        except Exception as e:
            snap_id = getattr(snapshot, 'id', None)
            logger.warning(f'Skipping malformed desktop prompt {snap_id} for uid={uid}: {sanitize(str(e))}')
            continue
    prompts.sort(key=lambda p: p.id)
    return DesktopPromptsResponse(prompts=prompts)
