"""Content-free note receipts and a shared deadline for episode repairs."""

import logging
from functools import wraps
from time import monotonic
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)
_current: ContextVar[Any] = ContextVar('notes_run', default=None)


class NotesRun:
    def __init__(self, arm: str):
        self.arm = arm
        self.started = monotonic()
        self.calls = 0
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'cached_tokens': 0}
        self.known = {key: True for key in self.usage}
        self.violations: set[str] = set()
        self.fallback_to_best_note = False
        self.claim_count = 0
        self.error = False
        self.vacuity = False

    def remaining(self, budget: float) -> float:
        return max(0.0, budget - (monotonic() - self.started))

    def invoke(self, model: Any, messages: Any) -> Any:
        self.calls += 1
        try:
            response = model.invoke(messages)
        except Exception:
            self.error = True
            self.known = {key: False for key in self.usage}
            raise
        usage = getattr(response, 'usage_metadata', None) or {}
        for key in ('input_tokens', 'output_tokens'):
            if key not in usage:
                self.known[key] = False
            else:
                self.usage[key] += usage[key] or 0
        cached = (usage.get('input_token_details') or {}).get('cache_read')
        if cached is None:
            self.known['cached_tokens'] = False
        else:
            self.usage['cached_tokens'] += cached
        return response

    def instrument(self, model):
        run = self

        class ObservedModel:
            def invoke(self, messages):
                return run.invoke(model, messages)

        return ObservedModel()

    def emit(self):
        logger.info(
            'conversation_notes_receipt arm=%s input_tokens=%s output_tokens=%s cached_tokens=%s '
            'latency_seconds=%.3f retry_count=%s violations=%s vacuity=%s claim_count=%s '
            'fallback_to_best_note=%s errors=%s',
            self.arm,
            *(self.usage[key] if self.calls and self.known[key] else None for key in self.usage),
            monotonic() - self.started,
            max(0, self.calls - 1),
            ','.join(sorted(self.violations)) or 'none',
            self.vacuity,
            self.claim_count,
            self.fallback_to_best_note,
            int(self.error),
        )


def current_run() -> NotesRun | None:
    return _current.get()


def observe_notes(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        run = NotesRun('episode' if kwargs.get('episode_evidence') is not None else 'baseline')
        token = _current.set(run)
        try:
            result = fn(*args, **kwargs)
            from utils.conversations.episode_vacuity import is_vacuous_note

            run.vacuity = is_vacuous_note(result)
            run.claim_count = len(result.note_claims or [])
            return result
        except Exception:
            run.error = True
            raise
        finally:
            run.emit()
            _current.reset(token)

    return wrapped
