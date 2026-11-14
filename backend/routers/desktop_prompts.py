import hashlib
import logging
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
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


def _safe_int(val: Any, default: int = 0) -> int:
    """Safely coerces numeric strings, ints, or floats to int, explicitly rejecting
    booleans, NaNs, infinities, and unparseable types."""
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return default
        return int(val)
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return default
        try:
            f = float(s)
            if math.isnan(f) or math.isinf(f):
                return default
            return int(f)
        except (ValueError, OverflowError):
            return default
    return default


def rollout_bucket(uid: str, prompt_id: str) -> int:
    """Stable 0-99 bucket per (user, prompt): percentage rollouts hold steady
    across polls instead of re-rolling, and a user lands in different buckets
    for different prompts."""
    pid = str(prompt_id) if prompt_id is not None else ''
    u = str(uid) if uid is not None else ''
    digest = hashlib.sha256(f'{pid}:{u}'.encode()).hexdigest()
    return int(digest[:8], 16) % 100


def prompt_matches_audience(doc: Dict[str, Any], uid: str, channel: str, build: int) -> bool:
    if not isinstance(doc, dict):
        return False

    raw_audience = doc.get('audience')
    audience = raw_audience if isinstance(raw_audience, dict) else {}

    raw_channels = audience.get('channels')
    if raw_channels is not None:
        if not isinstance(raw_channels, (list, tuple, set)) or isinstance(raw_channels, (str, bytes)):
            # Malformed channel list (e.g. non-sequence or string 'stable-beta'); reject audience match
            return False
        if raw_channels:
            str_channels = {str(c) for c in raw_channels}
            if channel not in raw_channels and channel not in str_channels:
                return False

    min_build = _safe_int(audience.get('min_build'), 0)
    build_val = _safe_int(build, 0)
    if build_val and min_build and build_val < min_build:
        return False

    raw_rollout = audience.get('rollout_pct')
    if raw_rollout is None:
        rollout_pct = 100
    else:
        rollout_pct = max(0, min(100, _safe_int(raw_rollout, 100)))

    prompt_id = doc.get('id')
    if not prompt_id:
        return False
    return rollout_bucket(uid, str(prompt_id)) < rollout_pct


def spec_from_doc(doc: Dict[str, Any]) -> Optional[DesktopPromptSpec]:
    if not isinstance(doc, dict):
        return None

    prompt_type = doc.get('type')
    question = doc.get('question')
    prompt_id = doc.get('id')

    if not prompt_id or prompt_type not in ALLOWED_TYPES or not question:
        return None

    if not isinstance(prompt_type, str) or not isinstance(question, (str, int, float)):
        return None

    prompt_id_str = str(prompt_id).strip()
    question_str = str(question).strip()
    if not prompt_id_str or not question_str:
        return None

    raw_trigger = doc.get('trigger')
    trigger = raw_trigger if isinstance(raw_trigger, dict) else {}

    raw_cta = doc.get('cta')
    cta = raw_cta if isinstance(raw_cta, dict) else {}

    raw_options = doc.get('options')
    if isinstance(raw_options, (list, tuple)) and not isinstance(raw_options, (str, bytes)):
        options = [str(o) for o in raw_options if o is not None][:6]
    else:
        options = []

    cta_label = str(cta['label']) if isinstance(cta.get('label'), (str, int, float)) else None
    cta_url = str(cta['url']) if isinstance(cta.get('url'), (str, int, float)) else None

    raw_kind = trigger.get('kind')
    trigger_kind = str(raw_kind) if raw_kind is not None else 'app_launch'
    trigger_count = max(0, _safe_int(trigger.get('count'), 0))
    max_per_day = max(1, _safe_int(doc.get('max_per_day'), 1))

    return DesktopPromptSpec(
        id=prompt_id_str,
        type=prompt_type,
        question=question_str,
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
    except Exception as e:
        logger.error(f"Failed to load desktop prompts: {sanitize(str(e))}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load desktop prompts",
        )

    prompts: List[DesktopPromptSpec] = []
    for snapshot in snapshots:
        try:
            doc = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else None
            if not isinstance(doc, dict):
                doc = {}
            doc.setdefault('id', getattr(snapshot, 'id', ''))
            if not prompt_matches_audience(doc, uid, channel, build):
                continue
            spec = spec_from_doc(doc)
            if spec is not None:
                prompts.append(spec)
        except Exception as exc:
            snap_id = getattr(snapshot, 'id', 'unknown')
            logger.warning(
                f"Skipping malformed desktop prompt snapshot {sanitize(str(snap_id))}: {sanitize(str(exc))}"
            )
            continue

    prompts.sort(key=lambda p: p.id)
    return DesktopPromptsResponse(prompts=prompts)
