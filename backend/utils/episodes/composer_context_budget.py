"""One context deadline, including provider retries and non-cooperative SDKs."""

import threading
import time
from typing import Callable

from config.episodes import COMPOSER_CONTEXT_TIMEOUT_SECONDS


def _fallback(reason: str) -> None:
    from utils.observability.fallback import record_fallback

    record_fallback(
        component='conversation_notes',
        from_mode='episode_memories',
        to_mode='without_memories',
        reason=reason,
        outcome='degraded',
    )


def _submit(worker: Callable[[], None]) -> None:
    from utils.executors import get_context_executor, submit_with_context

    submit_with_context(get_context_executor(), worker)


def bounded_gather(
    load: Callable[[float, Callable[[str], None]], tuple[str, str]], fallback_profile: str
) -> tuple[str, str]:
    """Bound the caller even if an SDK ignores its remaining-time RPC timeout.

    The existing optional-context executor has four workers and no queue. Slots
    stay owned until those workers exit; busy callers fail empty immediately.
    Providers share the absolute deadline and check it before further IO.
    Late results are discarded, never cached or published to another compose.
    """
    deadline = time.monotonic() + COMPOSER_CONTEXT_TIMEOUT_SECONDS
    completed = threading.Event()
    lock = threading.Lock()
    state = {'profile': fallback_profile, 'memories': '', 'reason': ''}

    def publish(profile: str) -> None:
        with lock:
            if time.monotonic() < deadline:
                state['profile'] = profile

    def worker() -> None:
        try:
            profile, memories = load(deadline, publish)
            with lock:
                if time.monotonic() < deadline:
                    state.update(profile=profile, memories=memories)
        except Exception as error:
            from utils.other.list_budget import ListReadBudgetExhausted

            reason = 'transport_error'
            if isinstance(error, TimeoutError) or (
                isinstance(error, ListReadBudgetExhausted) and error.reason == 'deadline'
            ):
                reason = 'timeout'
            elif isinstance(error, ListReadBudgetExhausted):
                reason = 'provider_budget_exhausted'
            with lock:
                state['reason'] = reason
        finally:
            completed.set()

    try:
        _submit(worker)
    except Exception:
        _fallback('capacity_full')
        return fallback_profile, ''
    completed.wait(max(0.0, deadline - time.monotonic()))
    with lock:
        reason = 'timeout' if not completed.is_set() or time.monotonic() >= deadline else state['reason']
        if reason:
            _fallback(reason)
        return state['profile'], '' if reason else state['memories']
