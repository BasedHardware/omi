"""Live global kill switch, eligibility and hard all-user Dream ceilings."""

import math
import os
from dataclasses import dataclass
from config.plan_catalog import PAID_PLAN_IDS

AUTO = frozenset(
    {
        'spelling',
        'title',
        'overview',
        'vocabulary',
        'merge_memories',
        'retire_memory',
        'supersede_memory',
        'dismiss_person',
        'merge_people',
        'merge_tasks',
        'retire_task',
        'merge_conversations',
        'set_language',
    }
)
SUGGEST = frozenset({'close_task', 'memory', 'entity_summary'})
KNOWN_KINDS = AUTO | SUGGEST
SUGGESTIONS_PER_DAY = 3
PASS_TIMEOUT_SECONDS = 1620
DRAIN_TIMEOUT_SECONDS = 1680
HTTP_TIMEOUT_SECONDS = 1710
LEASE_RECLAIM_MARGIN_SECONDS = 60
FINISH_MARGIN_SECONDS = 30


def enabled():
    return os.getenv('DREAM_AGENT_ENABLED', 'false').strip().lower() == 'true'


def mode():
    return 'on' if enabled() else 'off'


def eligibility():
    value = os.getenv('DREAM_AGENT_ELIGIBILITY', 'all').strip().lower()
    return value if value in {'all', 'paid', 'allowlist'} else 'invalid'


def _allowlisted(uid):
    return uid in {item.strip() for item in os.getenv('DREAM_AGENT_UID_ALLOWLIST', '').split(',') if item.strip()}


def may_be_eligible(uid):
    return (
        bool(uid)
        and not uid.startswith('dream-canary-')
        and eligibility() != 'invalid'
        and (eligibility() != 'allowlist' or _allowlisted(uid))
    )


def eligible(uid, user):
    if not may_be_eligible(uid) or user.get('dream_canary') or user.get('deleted') or user.get('deletion_requested_at'):
        return False
    policy = eligibility()
    return (
        policy == 'all'
        or (policy == 'allowlist' and _allowlisted(uid))
        or (policy == 'paid' and (user.get('subscription') or {}).get('plan', user.get('plan', '')) in PAID_PLAN_IDS)
    )


def auto_apply_kinds(uid=None):
    return AUTO


def apply_policy(kind, automatic):
    if kind not in KNOWN_KINDS:
        raise ValueError('Unknown dream edit kind')
    return 'auto' if kind in automatic else 'suggest'


def canary_uid() -> str:
    value = os.getenv('DREAM_AGENT_CANARY_UID', '').strip()
    # Reserved synthetic namespace; a user document marker is also required.
    return value if value.startswith('dream-canary-') and '/' not in value and len(value) <= 128 else ''


def canary_eligible(uid: str, user: dict) -> bool:
    return bool(canary_uid()) and uid == canary_uid() and user.get('dream_canary') is True


def self_report_enabled() -> bool:
    return enabled()


def number(key: str, default: float) -> float:
    value = float(os.getenv(key, str(default)))
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid dream budget: ' + key)
    return value


@dataclass(frozen=True)
class Caps:
    tokens: int = 256000
    passes: int = 2
    edits: int = 25
    daily_usd: float = 10.0
    global_daily_usd: float = 100.0
    tokens_per_minute: int = 2000000
    max_usd_per_token: float = 0.00001
    undo_rate: float = 0.2
    undo_min_samples: int = 10
    anonymous_k: int = 20
    manual_runs: int = 3
    completion_tokens: int = 4096

    @classmethod
    def from_env(cls):
        return cls(
            tokens=int(number('DREAM_AGENT_TOKENS_PER_PASS', 256000)),
            passes=int(number('DREAM_AGENT_PASSES_PER_DAY', 2)),
            edits=int(number('DREAM_AGENT_EDITS_PER_PASS', 25)),
            daily_usd=number('DREAM_AGENT_DAILY_USD', 10),
            global_daily_usd=number('DREAM_AGENT_GLOBAL_DAILY_USD', 100),
            tokens_per_minute=int(number('DREAM_AGENT_TOKENS_PER_MINUTE', 2000000)),
            max_usd_per_token=number('DREAM_AGENT_MAX_USD_PER_TOKEN', 0.00001),
            undo_rate=number('DREAM_AGENT_UNDO_RATE', 0.2),
            undo_min_samples=int(number('DREAM_AGENT_UNDO_MIN_SAMPLES', 10)),
            anonymous_k=max(2, int(number('DREAM_AGENT_FEEDBACK_K', 20))),
            manual_runs=int(number('DREAM_AGENT_MANUAL_RUNS_PER_DAY', 3)),
        )

    @property
    def reservation_usd(self):
        return self.tokens * self.max_usd_per_token


def concurrency():
    return max(1, min(8, int(number('DREAM_AGENT_CONCURRENCY', 2))))
