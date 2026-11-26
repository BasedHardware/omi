"""One context deadline, including provider retries and non-cooperative SDKs."""

import logging
import threading
import time
from typing import Callable

from config.episodes import COMPOSER_CONTEXT_TIMEOUT_SECONDS
from config.summary_context import failure_details
from utils.executors import get_context_executor, submit_with_context
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudgetExhausted

logger = logging.getLogger(__name__)


def _fallback(reason: str) -> None:
    record_fallback(
        component='conversation_notes',
        from_mode='episode_memories',
        to_mode='without_memories',
        reason=reason,
        outcome='degraded',
    )


def _submit(worker: Callable[[], None]) -> None:
    submit_with_context(get_context_executor(), worker)


def bounded_gather(load: Callable[[float], tuple[str, str]], fallback_profile: str) -> tuple[str, str]:
    """Bound the caller even if an SDK ignores its remaining-time RPC timeout.

    The existing optional-context executor has four workers and no queue. Slots
    stay owned until those workers exit; busy callers fail empty immediately.
    Providers share the absolute deadline and check it before further IO.
    Late results are discarded, never cached or published to another compose.
    """
    deadline = time.monotonic() + COMPOSER_CONTEXT_TIMEOUT_SECONDS
    completed = threading.Event()
    lock = threading.Lock()
    state = {
        'profile': fallback_profile,
        'memories': '',
        'reason': '',
        'stage': 'budget',
        'exception_type': 'TimeoutError',
    }

    def worker() -> None:
        try:
            profile, memories = load(deadline)
            with lock:
                if time.monotonic() < deadline:
                    state.update(profile=profile, memories=memories)
        except Exception as error:
            reason = 'transport_error'
            if isinstance(error, TimeoutError) or (
                isinstance(error, ListReadBudgetExhausted) and error.reason == 'deadline'
            ):
                reason = 'timeout'
            elif isinstance(error, ListReadBudgetExhausted):
                reason = 'provider_budget_exhausted'
            with lock:
                state['reason'] = reason
                state['stage'], state['exception_type'] = failure_details(error)
                if isinstance(error, ListReadBudgetExhausted):
                    state['stage'] = 'budget'
        finally:
            completed.set()

    try:
        _submit(worker)
    except Exception as error:
        logger.warning('event=episode_context_fallback stage=budget exception_type=%s', type(error).__name__)
        _fallback('capacity_full')
        return fallback_profile, ''
    completed.wait(max(0.0, deadline - time.monotonic()))
    with lock:
        reason = 'timeout' if not completed.is_set() or time.monotonic() >= deadline else state['reason']
        if reason:
            logger.warning(
                'event=episode_context_fallback stage=%s exception_type=%s', state['stage'], state['exception_type']
            )
            _fallback(reason)
            return fallback_profile, ''
        return state['profile'], state['memories']
