"""Listen WebSocket connect bootstrap — offload sync Firestore reads off the event loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import database.users as user_db
from utils.executors import db_executor, run_blocking
from utils.fair_use import (
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    get_enforcement_stage,
    is_dg_budget_exhausted,
)
from utils.subscription import has_transcription_credits
from utils.transcribe_decisions import (
    normalize_language,
    select_translation_language,
    should_force_single_language,
)
from utils.transcribe_store import get_user_transcription_preferences


@dataclass(frozen=True)
class ListenConnectBase:
    user_exists: bool
    user_has_credits: bool
    transcription_prefs: Dict[str, Any]
    fair_use_init_stage: Optional[str]
    fair_use_track_dg_usage: bool
    fair_use_dg_budget_exhausted: bool


@dataclass(frozen=True)
class ListenConnectContext:
    user_exists: bool
    user_has_credits: bool
    transcription_prefs: Dict[str, Any]
    single_language_mode: bool
    vocabulary: List[str]
    user_language_preference: str
    language: str
    translation_language: Optional[str]
    fair_use_init_stage: Optional[str]
    fair_use_track_dg_usage: bool
    fair_use_dg_budget_exhausted: bool


def project_listen_connect_decisions(
    *,
    language: str,
    onboarding_mode: bool,
    transcription_prefs: Dict[str, Any],
    stt_language: str,
) -> tuple[bool, List[str], str, Optional[str]]:
    single_language_mode = transcription_prefs.get('single_language_mode', False)
    vocabulary = list(transcription_prefs.get('vocabulary', []))
    user_language_preference = transcription_prefs.get('language', '')

    single_language_mode = should_force_single_language(onboarding_mode, single_language_mode)
    vocabulary = list({'Omi'} | set(vocabulary))
    normalized_language = normalize_language(language)
    translation_language = select_translation_language(
        single_language_mode=single_language_mode,
        stt_language=stt_language,
        language=normalized_language,
        user_language_preference=user_language_preference,
    )
    return single_language_mode, vocabulary, normalized_language, translation_language


async def load_listen_connect_base(
    uid: str,
    *,
    source: Optional[str],
    use_custom_stt: bool,
) -> ListenConnectBase:
    """Load connect-time Firestore state off the event loop."""
    user_exists = await run_blocking(db_executor, user_db.is_exists_user, uid)

    if use_custom_stt:
        user_has_credits = True
    else:
        user_has_credits = await run_blocking(db_executor, has_transcription_credits, uid, source=source)

    transcription_prefs = await run_blocking(db_executor, get_user_transcription_preferences, uid)

    fair_use_init_stage: Optional[str] = None
    fair_use_track_dg_usage = False
    fair_use_dg_budget_exhausted = False
    if FAIR_USE_ENABLED:
        fair_use_init_stage = await run_blocking(db_executor, get_enforcement_stage, uid)
        if fair_use_init_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
            fair_use_track_dg_usage = True
            fair_use_dg_budget_exhausted = await run_blocking(db_executor, is_dg_budget_exhausted, uid)

    return ListenConnectBase(
        user_exists=user_exists,
        user_has_credits=user_has_credits,
        transcription_prefs=transcription_prefs,
        fair_use_init_stage=fair_use_init_stage,
        fair_use_track_dg_usage=fair_use_track_dg_usage,
        fair_use_dg_budget_exhausted=fair_use_dg_budget_exhausted,
    )


def finalize_listen_connect_context(
    base: ListenConnectBase,
    *,
    language: str,
    onboarding_mode: bool,
    stt_language: str,
) -> ListenConnectContext:
    single_language_mode, vocabulary, normalized_language, translation_language = project_listen_connect_decisions(
        language=language,
        onboarding_mode=onboarding_mode,
        transcription_prefs=base.transcription_prefs,
        stt_language=stt_language,
    )
    return ListenConnectContext(
        user_exists=base.user_exists,
        user_has_credits=base.user_has_credits,
        transcription_prefs=base.transcription_prefs,
        single_language_mode=single_language_mode,
        vocabulary=vocabulary,
        user_language_preference=base.transcription_prefs.get('language', ''),
        language=normalized_language,
        translation_language=translation_language,
        fair_use_init_stage=base.fair_use_init_stage,
        fair_use_track_dg_usage=base.fair_use_track_dg_usage,
        fair_use_dg_budget_exhausted=base.fair_use_dg_budget_exhausted,
    )


async def load_listen_connect_context(
    uid: str,
    *,
    language: str,
    source: Optional[str],
    use_custom_stt: bool,
    onboarding_mode: bool,
    stt_language: str,
) -> ListenConnectContext:
    base = await load_listen_connect_base(uid, source=source, use_custom_stt=use_custom_stt)
    return finalize_listen_connect_context(
        base,
        language=language,
        onboarding_mode=onboarding_mode,
        stt_language=stt_language,
    )
