import hashlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
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
MAX_OPTIONS = 6
MAX_TEXT_LENGTH = 500


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


def _as_dict(value: Any) -> Dict[str, Any]:
    """Treat any non-dict nested document field as absent.

    `doc.get('audience') or {}` only guards falsy values: a legacy or
    hand-edited document that stores a string or list in `audience` /
    `trigger` / `cta` reached `.get(...)` and raised AttributeError, which
    failed the whole response for every desktop client.
    """
    return value if isinstance(value, dict) else {}


def _as_text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> Optional[str]:
    """Return a trimmed string, or None when the value is not usable text."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _as_str_list(value: Any, *, limit: Optional[int] = None) -> List[str]:
    """Return a list of trimmed strings; anything else is empty.

    A bare string is NOT a sequence of channels: `channel not in 'stable-beta'`
    is a substring test that silently admits the wrong audience, and
    `[str(o) for o in 'yes,no']` splits into single characters.
    """
    if not isinstance(value, (list, tuple)):
        return []
    items = [
        str(entry).strip() for entry in value if isinstance(entry, (str, int, float)) and not isinstance(entry, bool)
    ]
    items = [entry for entry in items if entry]
    return items[:limit] if limit is not None else items


def _as_int(value: Any, default: int) -> int:
    """Coerce to int, rejecting bools, NaN/inf and non-numeric strings.

    `build < min_build` raises TypeError when min_build is the string '12000',
    and `int(True)` silently yields 1 — both are config bugs, not audiences.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # NaN/inf cannot be compared against a build number.
        if value != value or value in (float('inf'), float('-inf')):
            return default
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (TypeError, ValueError):
            return default
    return default


def _as_percent(value: Any, default: int = 100) -> int:
    """Clamp a rollout percentage into 0..100; unusable values use the default."""
    pct = _as_int(value, default)
    return max(0, min(100, pct))


def rollout_bucket(uid: str, prompt_id: str) -> int:
    """Stable 0-99 bucket per (user, prompt): percentage rollouts hold steady
    across polls instead of re-rolling, and a user lands in different buckets
    for different prompts."""
    digest = hashlib.sha256(f'{prompt_id}:{uid}'.encode()).hexdigest()
    return int(digest[:8], 16) % 100


def prompt_matches_audience(doc: Dict[str, Any], uid: str, channel: str, build: int) -> bool:
    audience = _as_dict(doc.get('audience'))
    channels = _as_str_list(audience.get('channels'))
    if channels and channel not in channels:
        return False
    min_build = _as_int(audience.get('min_build'), 0)
    if build and min_build and build < min_build:
        return False
    rollout_pct = _as_percent(audience.get('rollout_pct'), 100)
    return rollout_bucket(uid, str(doc.get('id'))) < rollout_pct


def spec_from_doc(doc: Dict[str, Any]) -> Optional[DesktopPromptSpec]:
    prompt_id = _as_text(doc.get('id'), limit=128)
    prompt_type = _as_text(doc.get('type'), limit=32)
    question = _as_text(doc.get('question'))
    if not prompt_id or prompt_type not in ALLOWED_TYPES or not question:
        return None
    trigger = _as_dict(doc.get('trigger'))
    cta = _as_dict(doc.get('cta'))
    return DesktopPromptSpec(
        id=prompt_id,
        type=prompt_type,
        question=question,
        options=_as_str_list(doc.get('options'), limit=MAX_OPTIONS),
        cta_label=_as_text(cta.get('label'), limit=64),
        cta_url=_as_text(cta.get('url'), limit=512),
        trigger_kind=_as_text(trigger.get('kind'), limit=64) or 'app_launch',
        trigger_count=max(0, _as_int(trigger.get('count'), 0)),
        max_per_day=max(1, _as_int(doc.get('max_per_day'), 1)),
    )


@router.get('/v2/desktop/prompts', response_model=DesktopPromptsResponse)
def get_desktop_prompts(
    channel: str = 'stable',
    build: int = 0,
    uid: str = Depends(auth.get_current_user_uid),
) -> DesktopPromptsResponse:
    prompts: List[DesktopPromptSpec] = []
    try:
        snapshots = list_active_desktop_prompt_snapshots()
    except Exception as error:  # noqa: BLE001 - a prompt poll must never 500
        # Prompts are a best-effort overlay on app launch: a Firestore blip
        # should degrade to "no prompts", not break the desktop client.
        logger.error('desktop prompts read failed: %s', sanitize(error), exc_info=True)
        return DesktopPromptsResponse(prompts=[])

    for snapshot in snapshots:
        # One malformed document must not sink every other prompt, so the
        # guard is per snapshot rather than around the whole loop.
        try:
            doc = snapshot.to_dict() or {}
            if not isinstance(doc, dict):
                continue
            doc.setdefault('id', snapshot.id)
            if not prompt_matches_audience(doc, uid, channel, build):
                continue
            spec = spec_from_doc(doc)
            if spec is not None:
                prompts.append(spec)
        except Exception as error:  # noqa: BLE001 - skip the bad document
            logger.error(
                'skipping malformed desktop prompt %s: %s', getattr(snapshot, 'id', '?'), sanitize(error), exc_info=True
            )
            continue

    prompts.sort(key=lambda p: p.id)
    return DesktopPromptsResponse(prompts=prompts)
