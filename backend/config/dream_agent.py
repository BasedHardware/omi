"""Live global kill switch, eligibility and hard all-user Dream ceilings."""

from config.refactor_switches import default_off as rollout_default_off

import math
import os

from config.policy.batch import cohort_bucket

from config.rollout_cohorts import in_rollout_cohort, rollout_cohort_members, RolloutCohortUnavailable
from dataclasses import dataclass
from datetime import timedelta
from config.plan_catalog import PAID_PLAN_IDS

from utils.agent_capabilities.registry import AUTO, KINDS

SUGGEST = frozenset(name for name, spec in KINDS.items() if spec.default_policy == 'suggest')
KNOWN_KINDS = AUTO | SUGGEST
SUGGESTIONS_PER_DAY = 3
PASS_TIMEOUT_SECONDS = 1620
DRAIN_TIMEOUT_SECONDS = 1680
HTTP_TIMEOUT_SECONDS = 1710
LEASE_RECLAIM_MARGIN_SECONDS = 60
FINISH_MARGIN_SECONDS = 30


def enabled():
    from config.dream_control import allowed

    return (
        rollout_default_off('DREAM_AGENT_ENABLED', os.getenv('DREAM_AGENT_ENABLED', 'false').strip().lower() == 'true')
        and allowed()
    )


def mode():
    return 'on' if enabled() else 'off'


def eligibility():
    value = os.getenv('DREAM_AGENT_ELIGIBILITY', 'all').strip().lower()
    return value if value in {'all', 'paid', 'allowlist'} else 'invalid'


def allowlisted(uid):
    return in_rollout_cohort(uid, 'dream-agent')


def _allowlisted(uid):
    return allowlisted(uid)


def allowlist_uids():
    """Sorted allowlist; discovery reads only these owners under ``allowlist`` eligibility."""
    try:
        return list(rollout_cohort_members('dream-agent'))
    except RolloutCohortUnavailable:
        if eligibility() == 'allowlist':
            raise
        # A membership outage cannot veto declared all/paid eligibility. It
        # also cannot manufacture an allowlist exception to a paid percentage.
        return []


def paid_percent():
    """Share of paid owners in the Dream ramp; unset admits every paid owner, malformed admits none."""
    raw = os.getenv('DREAM_AGENT_PAID_PERCENT', '100').strip()
    if not raw.isascii() or not raw.isdigit() or int(raw) > 100:
        return 0
    return int(raw)


def in_paid_ramp(uid):
    """Stable per-owner bucket, so widening the percent only ever adds owners."""
    bucket = cohort_bucket(uid, 'dream-agent-paid', formula='modulo')
    return bucket < paid_percent()


def _paid_cohort(uid):
    # Listed owners stay in at any percent; the member list is cached, not read per owner.
    return in_paid_ramp(uid) or uid in allowlist_uids()


def hunt_interval(size_bucket):
    """Idle time before a pass with no dirty work hunts again; 24h (6h heavy) unless overridden."""
    default = 6.0 if size_bucket == 'heavy' else 24.0
    raw = os.getenv('DREAM_AGENT_HUNT_INTERVAL_HOURS', '').strip()
    try:
        hours = float(raw) if raw else default
    except ValueError:
        hours = default
    if not math.isfinite(hours) or hours <= 0:
        hours = default
    return timedelta(hours=min(hours, default))


def on_demand_enabled():
    return rollout_default_off(
        'DREAM_ON_DEMAND_ENABLED', os.getenv('DREAM_ON_DEMAND_ENABLED', '').strip().lower() in {'1', 'true', 'yes'}
    )


def admission_for(uid):
    """Gateway admission the backend asserts. Never taken from user input.

    On-demand is only for an allowlisted owner while ``DREAM_ON_DEMAND_ENABLED``
    is true. Every other owner, and allowlisted owners with the flag off, use
    reserved capacity.
    """
    try:
        listed = allowlisted(uid)
    except RolloutCohortUnavailable:
        listed = False  # Reserved capacity only; never invent spending authority.
    if listed and on_demand_enabled():
        return 'on_demand', True
    return 'reserved', False


def dream_journal_key(edit_key):
    return isinstance(edit_key, str) and (edit_key.startswith('agent:') or edit_key.startswith('dream:'))


def may_be_eligible(uid):
    return (
        bool(uid)
        and not uid.startswith('dream-canary-')
        and eligibility() != 'invalid'
        and (eligibility() != 'allowlist' or _allowlisted(uid))
        and (eligibility() != 'paid' or _paid_cohort(uid))
    )


def eligible(uid, user):
    if not may_be_eligible(uid) or user.get('dream_canary') or user.get('deleted') or user.get('deletion_requested_at'):
        return False
    policy = eligibility()
    return (
        policy == 'all'
        or (policy == 'allowlist' and _allowlisted(uid))
        or (
            policy == 'paid'
            and (
                uid in allowlist_uids()
                or (
                    in_paid_ramp(uid)
                    and (user.get('subscription') or {}).get('plan', user.get('plan', '')) in PAID_PLAN_IDS
                )
            )
        )
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
    tokens: int = 1000000
    passes: int = 2
    edits: int = 25
    daily_usd: float = 10.0
    expected_tokens: int = 12000
    tokens_per_minute: int = 2000000
    undo_rate: float = 0.2
    undo_min_samples: int = 10
    anonymous_k: int = 20
    manual_runs: int = 3
    # Main-lane reply ceiling. Gemini 3.x counts thinking inside it, so 4096 truncated medium-effort turns.
    completion_tokens: int = 32768
    verifier_completion_tokens: int = 4096

    @classmethod
    def from_env(cls):
        return cls(
            tokens=int(number('DREAM_AGENT_TOKENS_PER_PASS', 1000000)),
            passes=int(number('DREAM_AGENT_PASSES_PER_DAY', 2)),
            edits=int(number('DREAM_AGENT_EDITS_PER_PASS', 25)),
            daily_usd=number('DREAM_AGENT_DAILY_USD', 10),
            expected_tokens=int(number('DREAM_AGENT_EXPECTED_TOKENS', 12000)),
            tokens_per_minute=int(number('DREAM_AGENT_TOKENS_PER_MINUTE', 2000000)),
            undo_rate=number('DREAM_AGENT_UNDO_RATE', 0.2),
            undo_min_samples=int(number('DREAM_AGENT_UNDO_MIN_SAMPLES', 10)),
            anonymous_k=max(2, int(number('DREAM_AGENT_FEEDBACK_K', 20))),
            manual_runs=int(number('DREAM_AGENT_MANUAL_RUNS_PER_DAY', 3)),
        )


def concurrency():
    caps = Caps.from_env()
    derived = math.ceil(caps.tokens_per_minute / max(1, caps.expected_tokens) * 2)
    return max(1, min(512, int(number('DREAM_AGENT_CONCURRENCY', derived))))
