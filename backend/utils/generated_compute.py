"""Budget-only admission for user-owned generated and background work.

Do not use full plan authorization here: existing entrypoints retain their plan
policy when only funded-budget enforcement is enabled. The funded-processing
module owns allowance reads/caching and deliberately ignores request BYOK.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Concatenate, Iterator, ParamSpec, TypeVar

from fastapi import HTTPException

from config.stt_cap_dispatch import (
    execution_admission_enabled,
    execution_admission_configured as generated_compute_configured,
)

_generation_uid: ContextVar[str | None] = ContextVar('generated_compute_uid', default=None)

_P = ParamSpec('_P')
_T = TypeVar('_T')

_LLM_PROVIDERS = ('openai', 'openrouter', 'gemini', 'anthropic')


def generated_compute_allowed(
    uid: str | None,
    feature: str,
    *,
    allow_byok: bool = True,
    provider: str | None = None,
    firestore_client: Any = None,
) -> bool:
    """Check funded availability, exempting only an actual validated LLM key.

    ``provider`` pins direct-provider calls; feature-routed get_llm can select
    any of its supported customer-key providers. Images and other calls that
    never forward customer keys must set ``allow_byok=False``. Validation must
    belong to this UID, so a copied background context cannot fund another user.
    Both switches off returns before identity, keys, plan or allowance reads.
    """
    if not generated_compute_configured():
        return True
    if not execution_admission_enabled(uid or 'unknown', 'batch'):
        return True
    if not uid or uid == 'unknown':
        return False
    from utils import funded_processing

    if not funded_processing.consent_allows(uid):
        return False
    if allow_byok:
        from utils import byok

        if byok.has_validated_byok_keys() and byok.get_byok_uid() == uid:
            providers = (provider,) if provider in _LLM_PROVIDERS else (() if provider else _LLM_PROVIDERS)
            if any(byok.get_byok_key(candidate) for candidate in providers):
                return True
    # Billing/provider imports remain lazy so flag-off clients keep import purity.
    kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
    return funded_processing.processing_allowed(uid, **kwargs)


def require_generated_compute(
    uid: str | None,
    feature: str,
    *,
    allow_byok: bool = True,
    provider: str | None = None,
    firestore_client: Any = None,
) -> None:
    """Authenticated interactive admission; call before writes/fallback catches."""
    kwargs = {'firestore_client': firestore_client} if firestore_client is not None else {}
    if generated_compute_allowed(uid, feature, allow_byok=allow_byok, provider=provider, **kwargs):
        return
    now = datetime.now(timezone.utc)
    reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    raise HTTPException(
        status_code=402,
        detail={
            'error': 'usage_budget_exhausted',
            'trigger': 'usage_budget',
            'feature': feature,
            'reset_at': int(reset.timestamp()),
            'period_id': now.strftime('%Y-%m'),
            'choices': ['on_device', 'upgrade'],
        },
    )


def current_compute_uid(uid: str | None = None) -> str | None:
    """Resolve explicit, metering-scope or authenticated request ownership."""
    if uid or _generation_uid.get():
        return uid or _generation_uid.get()
    from utils.llm.usage_tracker import get_current_context

    context = get_current_context()
    if context and context.uid and context.uid != 'unknown':
        return context.uid
    from utils import byok

    return byok.get_byok_uid()


def current_generated_compute_allowed(feature: str, *, allow_byok: bool = True) -> bool:
    if not generated_compute_configured():
        return True
    return generated_compute_allowed(current_compute_uid(), feature, allow_byok=allow_byok)


def require_current_generated_compute(
    feature: str, *, uid: str | None = None, provider: str | None = None, allow_byok: bool = True
) -> None:
    if not generated_compute_configured():
        return
    require_generated_compute(current_compute_uid(uid), feature, provider=provider, allow_byok=allow_byok)


@contextmanager
def generated_compute_scope(uid: str) -> Iterator[None]:
    """Supply worker ownership without changing flag-off metering or prompts."""
    if not generated_compute_configured():
        yield
        return
    token = _generation_uid.set(uid)
    try:
        yield
    finally:
        _generation_uid.reset(token)


def generated_compute_scoped(function: Callable[Concatenate[str, _P], _T]) -> Callable[Concatenate[str, _P], _T]:
    """Bind a sync background entrypoint's first argument (UID) for model calls."""

    @wraps(function)
    def wrapped(uid: str, *args: _P.args, **kwargs: _P.kwargs) -> _T:
        with generated_compute_scope(uid):
            return function(uid, *args, **kwargs)

    return wrapped
