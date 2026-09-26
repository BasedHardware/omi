import hashlib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database._client import db
from utils.other import endpoints as auth

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
    channels = audience.get('channels') or []
    if channels and channel not in channels:
        return False
    min_build = audience.get('min_build') or 0
    if build and min_build and build < min_build:
        return False
    rollout_pct = audience.get('rollout_pct')
    if rollout_pct is None:
        rollout_pct = 100
    return rollout_bucket(uid, str(doc.get('id'))) < int(rollout_pct)


def spec_from_doc(doc: Dict[str, Any]) -> Optional[DesktopPromptSpec]:
    prompt_type = doc.get('type')
    question = doc.get('question')
    prompt_id = doc.get('id')
    if not prompt_id or prompt_type not in ALLOWED_TYPES or not question:
        return None
    trigger = doc.get('trigger') or {}
    cta = doc.get('cta') or {}
    return DesktopPromptSpec(
        id=str(prompt_id),
        type=prompt_type,
        question=str(question),
        options=[str(o) for o in (doc.get('options') or [])][:6],
        cta_label=cta.get('label'),
        cta_url=cta.get('url'),
        trigger_kind=str(trigger.get('kind') or 'app_launch'),
        trigger_count=int(trigger.get('count') or 0),
        max_per_day=int(doc.get('max_per_day') or 1),
    )


@router.get('/v2/desktop/prompts', response_model=DesktopPromptsResponse)
def get_desktop_prompts(
    channel: str = 'stable',
    build: int = 0,
    uid: str = Depends(auth.get_current_user_uid),
) -> DesktopPromptsResponse:
    prompts: List[DesktopPromptSpec] = []
    for snapshot in db.collection(PROMPTS_COLLECTION).where('active', '==', True).limit(50).stream():
        doc = snapshot.to_dict() or {}
        doc.setdefault('id', snapshot.id)
        if not prompt_matches_audience(doc, uid, channel, build):
            continue
        spec = spec_from_doc(doc)
        if spec is not None:
            prompts.append(spec)
    prompts.sort(key=lambda p: p.id)
    return DesktopPromptsResponse(prompts=prompts)
