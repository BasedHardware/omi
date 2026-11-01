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
        self.tier = 'none'
        self.route_reason = 'none'
        self.tier_fallback = False
        self.escalated = False
        self.escalation_reason = 'below_threshold'
        self.words = 0
        self.screen_count = 0
        self.writer_deadline = 0
        self.configured_deadline = 0
        self.repair_disabled = False
        self.started = monotonic()
        self.calls = 0
        self.effort = 'default'
        self.requested_effort = 'default'
        self.thinking_max_input_bytes = 0
        self.estimated_input_bytes = 0
        self.claims_enabled = False
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'cached_tokens': 0, 'reasoning_tokens': 0}
        self.known = {key: True for key in self.usage}
        self.violations: set[str] = set()
        self.fallback_to_best_note = False
        self.claim_count = 0
        self.error = False
        self.model_errors = 0
        self.vacuity = False

    def configure_episode(self, settings):
        self.effort, self.claims_enabled = settings.effort, settings.claims
        self.requested_effort = settings.effort
        self.thinking_max_input_bytes = settings.thinking_max_input_bytes

    def remaining(self, budget: float) -> float:
        return max(0.0, budget - (monotonic() - self.started))

    def invoke(self, model: Any, messages: Any) -> Any:
        call_started = monotonic()
        self.calls += 1
        try:
            response = model.invoke(messages)
        except Exception:
            self.model_errors += 1
            self.known = {key: False for key in self.usage}
            raise
        if self.writer_deadline and monotonic() - call_started > self.writer_deadline:
            self.violations.add('writer_deadline_overrun')
            self.repair_disabled = True
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
        reasoning = (usage.get('output_token_details') or {}).get('reasoning')
        if reasoning is None:
            self.known['reasoning_tokens'] = False
        else:
            self.usage['reasoning_tokens'] += reasoning
        return response

    def instrument(self, model):
        run = self

        class ObservedModel:
            def invoke(self, messages):
                return run.invoke(model, messages)

        return ObservedModel()

    def emit(self):
        logger.info(
            'conversation_notes_receipt arm=%s input_tokens=%s output_tokens=%s cached_tokens=%s reasoning_tokens=%s '
            'latency_seconds=%.3f retry_count=%s violations=%s vacuity=%s claim_count=%s '
            'fallback_to_best_note=%s errors=%s effort=%s claims_enabled=%s model_errors=%s requested_effort=%s '
            'thinking_max_input_bytes=%s estimated_input_bytes=%s tier=%s route_reason=%s tier_fallback=%s '
            'writer_deadline_seconds=%s configured_deadline_seconds=%s '
            'escalated=%s escalation_reason=%s words=%s screen_count=%s',
            self.arm,
            *(self.usage[key] if self.calls and self.known[key] else None for key in self.usage),
            monotonic() - self.started,
            max(0, self.calls - 1),
            ','.join(sorted(self.violations)) or 'none',
            self.vacuity,
            self.claim_count,
            self.fallback_to_best_note,
            int(self.error),
            self.effort,
            self.claims_enabled,
            self.model_errors,
            self.requested_effort,
            self.thinking_max_input_bytes,
            self.estimated_input_bytes,
            self.tier,
            self.route_reason,
            self.tier_fallback,
            self.writer_deadline,
            self.configured_deadline,
            'true' if self.escalated else 'false',
            self.escalation_reason,
            self.words,
            self.screen_count,
        )


def current_run() -> NotesRun | None:
    return _current.get()


def observe_notes(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        run = NotesRun('baseline')
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
