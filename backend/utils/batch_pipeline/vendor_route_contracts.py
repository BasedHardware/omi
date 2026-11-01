"""Frozen contracts for all-vendor batch routing (slice A). No IO, no behavior.

Four build slices code against this module; none of them may change a name,
field or rule here without a bus post naming the affected slice:

* B (route table + selection + rollout) reads ``RouteTableLadder`` and
  ``capable_options``, and owns ``select_route`` and the cohort gates.
* C (vendor health) implements ``VendorHealth.allows``.
* D (multi-vendor provider stage + failover) persists ``VendorAttempt``
  records under the ``check_new_attempt`` bounds and owns ``vendor_held``.
* E (GPU floor + capacity) sizes the floor that ``gpu_floor_percent`` feeds.

Capability stays code-owned in ``config.stt_provider_policy``: a table may only
order and price routes that policy admits on the ``prerecorded`` surface, so a
bad table degrades to today's routing, never to an unauthorized vendor. Prices,
caps, the GPU floor and quality rows are table values, never constants here.

Vendor speaker turns stay discarded on the vendor route (words-only, like
recovered units): ``speaker_turns`` is reserved with the single value
``'discard'`` so a later change can add a value without a schema bump.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, ClassVar, Final, Literal, Mapping, Protocol

from config.stt_provider_policy import (
    STTServingSurface,
    normalized_stt_language,
    parakeet_supports_language,
    provider_is_enabled,
)
from utils.observability.reasons import (
    VendorAttemptOutcome,
    VendorHealthReason,
    VendorHoldReason,
    VendorRouteTableOutcome,
)

SCHEMA_VERSION: Final = 1

# --- routes ---------------------------------------------------------------------------------------

RouteName = Literal['gpu', 'modulate', 'soniox']
GPU: Final = 'gpu'
MODULATE: Final = 'modulate'
SONIOX: Final = 'soniox'
ROUTES: Final[frozenset[str]] = frozenset({GPU, MODULATE, SONIOX})
VENDOR_SERVICES: Final[frozenset[str]] = frozenset({MODULATE, SONIOX})
# Lead requirement (11-01): Soniox async lists $0.10/h, so it is failover capacity only and
# selection never picks it as cheapest. A table that clears the flag is malformed.
FAILOVER_ONLY_SERVICES: Final[frozenset[str]] = frozenset({SONIOX})

Selection = Literal['cheapest', 'ordered']
SELECTIONS: Final[frozenset[str]] = frozenset({'cheapest', 'ordered'})
QualityTier = Literal['accepted', 'fallback', 'unproven']
QUALITY_TIERS: Final[frozenset[str]] = frozenset({'accepted', 'fallback', 'unproven'})
SPEAKER_TURNS: Final[frozenset[str]] = frozenset({'discard'})

# Row keys: an exact normalized language, one of two capability classes, or the default.
DEFAULT_CLASS: Final = '*'
GPU_SUPPORTED_CLASS: Final = 'gpu_supported'
GPU_UNSUPPORTED_CLASS: Final = 'gpu_unsupported'
_NAMED_CLASSES = frozenset({DEFAULT_CLASS, GPU_SUPPORTED_CLASS, GPU_UNSUPPORTED_CLASS})
_LANGUAGE = re.compile(r'[a-z]{2,3}|multi', re.ASCII)
_TOKEN = re.compile(r'[a-z0-9][a-z0-9._-]{0,39}', re.ASCII)
# Sanity bound only (rejects unit mistakes such as cents or $/minute); not a price.
MAX_PRICE_USD_PER_AUDIO_HOUR: Final = 10.0


class RouteTableInvalid(ValueError):
    """A route table failed validation. Messages are fixed text, never config content."""


def normalized_language(language: str | None) -> str:
    """The language key selection uses: unknown is ``multi``, as ``provider_stt.resolve_route``."""
    return normalized_stt_language(language) or 'multi'


def route_capable(route: str, language: str | None) -> bool:
    """Code-owned capability: GPU iff deployed Parakeet serves it; a vendor iff policy admits it.

    Vendors identify the language themselves (Modulate auto-detect, Soniox unified model), so
    vendor capability is surface admission only; tables narrow it per language class.

    Soniox is not admitted on ``prerecorded`` today (only ``streaming`` and ``held_recovery``), so
    it is never capable here and failover has no Soniox candidate until slice D adds that
    admission to ``config.stt_provider_policy`` alongside its prerecorded adapter. That
    reviewed policy change, not a table edit, is what enables Soniox failover.
    """
    if route == GPU:
        return parakeet_supports_language(STTServingSurface.PRERECORDED, normalized_language(language))
    if route in VENDOR_SERVICES:
        return provider_is_enabled(route, STTServingSurface.PRERECORDED)
    return False


def _finite(value: Any, *, upper: float | None = None, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise RouteTableInvalid('nonnegative finite number required')
    if upper is not None and value > upper:
        raise RouteTableInvalid('number above bound')
    return float(value)


def _exact_keys(raw: Any, keys: frozenset[str], what: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or frozenset(raw) != keys:
        raise RouteTableInvalid(f'{what} requires exactly its schema keys')
    return raw


@dataclass(frozen=True)
class RouteConfig:
    """Per-route economics and limits. Every key is required; ``None`` is an explicit choice."""

    price_usd_per_audio_hour: float | None
    daily_audio_hours_cap: float | None  # vendors only; reaching it makes the route unhealthy, never an error
    monthly_budget_usd: float | None  # vendors only; Soniox org budget class
    failover_only: bool
    speaker_turns: str = 'discard'

    KEYS: ClassVar[frozenset[str]] = frozenset(
        {'price_usd_per_audio_hour', 'daily_audio_hours_cap', 'monthly_budget_usd', 'failover_only', 'speaker_turns'}
    )

    @classmethod
    def from_dict(cls, route: str, raw: Any) -> 'RouteConfig':
        raw = _exact_keys(raw, cls.KEYS, 'route config')
        if not isinstance(raw['failover_only'], bool):
            raise RouteTableInvalid('failover_only must be a boolean')
        if raw['speaker_turns'] not in SPEAKER_TURNS:
            raise RouteTableInvalid('speaker_turns is reserved: only discard')
        config = cls(
            price_usd_per_audio_hour=_finite(
                raw['price_usd_per_audio_hour'], upper=MAX_PRICE_USD_PER_AUDIO_HOUR, allow_none=True
            ),
            daily_audio_hours_cap=_finite(raw['daily_audio_hours_cap'], allow_none=True),
            monthly_budget_usd=_finite(raw['monthly_budget_usd'], allow_none=True),
            failover_only=raw['failover_only'],
            speaker_turns=raw['speaker_turns'],
        )
        if route == GPU and (
            config.daily_audio_hours_cap is not None or config.monthly_budget_usd is not None or config.failover_only
        ):
            raise RouteTableInvalid('gpu takes no spend cap and is never failover-only')
        if route in FAILOVER_ONLY_SERVICES and not config.failover_only:
            raise RouteTableInvalid('this vendor is failover capacity only')
        return config


@dataclass(frozen=True)
class RouteOption:
    route: RouteName
    quality_tier: QualityTier
    quality_source: str  # bounded evidence token; gaps are 'unproven' rows, never guesses

    KEYS: ClassVar[frozenset[str]] = frozenset({'route', 'quality_tier', 'quality_source'})

    @classmethod
    def from_dict(cls, raw: Any) -> 'RouteOption':
        raw = _exact_keys(raw, cls.KEYS, 'route option')
        if raw['route'] not in ROUTES:
            raise RouteTableInvalid('closed route required')
        if raw['quality_tier'] not in QUALITY_TIERS:
            raise RouteTableInvalid('closed quality tier required')
        if not isinstance(raw['quality_source'], str) or not _TOKEN.fullmatch(raw['quality_source']):
            raise RouteTableInvalid('bounded quality source token required')
        return cls(raw['route'], raw['quality_tier'], raw['quality_source'])


@dataclass(frozen=True)
class RouteRow:
    language_class: str
    options: tuple[RouteOption, ...]  # preference order for 'ordered'; candidate set for 'cheapest'

    KEYS: ClassVar[frozenset[str]] = frozenset({'language_class', 'options'})

    @classmethod
    def from_dict(cls, raw: Any) -> 'RouteRow':
        raw = _exact_keys(raw, cls.KEYS, 'route row')
        language_class = raw['language_class']
        if not isinstance(language_class, str) or not (
            language_class in _NAMED_CLASSES or _LANGUAGE.fullmatch(language_class)
        ):
            raise RouteTableInvalid('language class must be *, a capability class or a normalized language')
        if not isinstance(raw['options'], list) or not raw['options']:
            raise RouteTableInvalid('a row needs at least one route option')
        options = tuple(RouteOption.from_dict(option) for option in raw['options'])
        if len({option.route for option in options}) != len(options):
            raise RouteTableInvalid('a row names each route at most once')
        routes = {option.route for option in options}
        # A GPU option that can never be capable is an unsafe-language row (T4), not a preference.
        if GPU in routes and (
            language_class == GPU_UNSUPPORTED_CLASS
            or (_LANGUAGE.fullmatch(language_class) and not route_capable(GPU, language_class))
        ):
            raise RouteTableInvalid('gpu option on a language the deployed Parakeet cannot serve')
        return cls(language_class, options)


@dataclass(frozen=True)
class RouteTable:
    schema_version: int
    table_version: str  # bounded id stamped on decisions and attempts
    selection: Selection
    gpu_floor_percent: float  # stable owner-hash share always GPU-first where capable (cohort GPU_FLOOR_COHORT)
    routes: Mapping[str, RouteConfig]
    rows: tuple[RouteRow, ...]

    KEYS: ClassVar[frozenset[str]] = frozenset(
        {'schema_version', 'table_version', 'selection', 'gpu_floor_percent', 'routes', 'rows'}
    )

    @classmethod
    def from_dict(cls, raw: Any) -> 'RouteTable':
        raw = _exact_keys(raw, cls.KEYS, 'route table')
        if type(raw['schema_version']) is not int or raw['schema_version'] != SCHEMA_VERSION:
            raise RouteTableInvalid('unsupported schema version')
        if not isinstance(raw['table_version'], str) or not _TOKEN.fullmatch(raw['table_version']):
            raise RouteTableInvalid('bounded table version token required')
        if raw['selection'] not in SELECTIONS:
            raise RouteTableInvalid('closed selection required')
        floor = _finite(raw['gpu_floor_percent'], upper=100.0)
        if not isinstance(raw['routes'], Mapping) or not raw['routes'] or not set(raw['routes']) <= ROUTES:
            raise RouteTableInvalid('routes must map closed route names')
        routes = {route: RouteConfig.from_dict(route, config) for route, config in raw['routes'].items()}
        if not isinstance(raw['rows'], list) or not raw['rows']:
            raise RouteTableInvalid('rows required')
        rows = tuple(RouteRow.from_dict(row) for row in raw['rows'])
        classes = [row.language_class for row in rows]
        if len(set(classes)) != len(classes):
            raise RouteTableInvalid('duplicate language class')
        if DEFAULT_CLASS not in classes:
            raise RouteTableInvalid('a default * row is required')
        for row in rows:
            if any(option.route not in routes for option in row.options):
                raise RouteTableInvalid('row names a route without a route config')
            if all(routes[option.route].failover_only for option in row.options):
                raise RouteTableInvalid('a row needs a route that is not failover-only')
        if raw['selection'] == 'cheapest' and any(
            config.price_usd_per_audio_hour is None for config in routes.values()
        ):
            raise RouteTableInvalid('cheapest selection requires a price on every route')
        return cls(SCHEMA_VERSION, raw['table_version'], raw['selection'], floor or 0.0, routes, rows)

    def row_for(self, language: str | None) -> RouteRow:
        """Exact language row, else its capability class row, else ``*``."""
        normalized = normalized_language(language)
        by_class = {row.language_class: row for row in self.rows}
        capability_class = GPU_SUPPORTED_CLASS if route_capable(GPU, normalized) else GPU_UNSUPPORTED_CLASS
        return by_class.get(normalized) or by_class.get(capability_class) or by_class[DEFAULT_CLASS]


def capable_options(table: RouteTable, language: str | None) -> tuple[RouteOption, ...]:
    """The row's options that code-owned capability admits, in row order. Empty means no route.

    Selection (slice B) applies health, price, failover-only and the GPU floor to this set; it
    must never consider an option outside it.
    """
    return tuple(option for option in table.row_for(language).options if route_capable(option.route, language))


# Terminal rung of the ladder and the kill-switch target: today's routing exactly. GPU for every
# language deployed Parakeet serves, Modulate only where it cannot (provider_stt.resolve_route).
BUILTIN_TABLE: Final = RouteTable.from_dict(
    {
        'schema_version': SCHEMA_VERSION,
        'table_version': 'builtin',
        'selection': 'ordered',
        'gpu_floor_percent': 0.0,
        'routes': {
            GPU: {
                'price_usd_per_audio_hour': None,
                'daily_audio_hours_cap': None,
                'monthly_budget_usd': None,
                'failover_only': False,
                'speaker_turns': 'discard',
            },
            MODULATE: {
                'price_usd_per_audio_hour': None,
                'daily_audio_hours_cap': None,
                'monthly_budget_usd': None,
                'failover_only': False,
                'speaker_turns': 'discard',
            },
        },
        'rows': [
            {
                'language_class': DEFAULT_CLASS,
                'options': [
                    {'route': GPU, 'quality_tier': 'accepted', 'quality_source': 'legacy_parity'},
                    {'route': MODULATE, 'quality_tier': 'accepted', 'quality_source': 'legacy_parity'},
                ],
            }
        ],
    }
)


class RouteTableLadder:
    """Configured -> last valid -> builtin. Process-local; one per process.

    ``None`` (unset or kill switch) is a deliberate choice and serves the builtin table without
    touching last-valid. Anything else that fails validation serves the last valid table.
    """

    def __init__(self) -> None:
        self._last_valid: RouteTable | None = None

    def resolve(self, raw: Any) -> tuple[RouteTable, VendorRouteTableOutcome]:
        if raw is None:
            return BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN
        try:
            table = RouteTable.from_dict(raw)
        except (ValueError, TypeError, KeyError, AttributeError):
            if self._last_valid is not None:
                return self._last_valid, VendorRouteTableOutcome.LAST_VALID
            return BUILTIN_TABLE, VendorRouteTableOutcome.BUILTIN
        self._last_valid = table
        return table, VendorRouteTableOutcome.CONFIGURED


# --- health (slice C implements) ------------------------------------------------------------------


class VendorHealth(Protocol):
    """``allows(service) -> (allowed, reason)``.

    * Never raises and never blocks on the network (cached cross-pod state; a failed read
      degrades to process-local state, and only if that fails too returns
      ``(False, STATE_UNAVAILABLE)``: fail toward GPU or ``vendor_held``, never a dead vendor).
    * ``(False, ...)`` means: mint no new intent for this service now. In-flight attempts finish.
    * ``HALF_OPEN_PROBE`` is ``(True, ...)`` for exactly the probe the breaker admits.
    * Reaching a daily audio-hour cap or monthly budget is ``(False, DAILY_CAP_REACHED |
      MONTHLY_BUDGET_REACHED)``: unhealthy, never an error.
    * ``gpu`` is always ``(True, HEALTHY)``: GPU capacity is the ring's wait, not health.
    """

    def allows(self, service: str) -> tuple[bool, VendorHealthReason]: ...


class AlwaysHealthy:
    """Stand-in for slices B and D until slice C lands."""

    def allows(self, service: str) -> tuple[bool, VendorHealthReason]:
        return True, VendorHealthReason.HEALTHY


# --- per-attempt intent (slice D implements) ------------------------------------------------------

# Paid-once per vendor: at most one billable attempt per service and two billable attempts per
# unit (first vendor + one failover vendor). Unbilled refusals (the vendor declined before
# processing) do not spend the service, but every attempt is a record and records are bounded.
# SILENCE is unbilled only when our VAD skipped the request (``audio_seconds == 0``); audio that
# was sent is billable whatever came back.
MAX_BILLABLE_ATTEMPTS: Final = 2
MAX_ATTEMPT_RECORDS: Final = 4
UNBILLED_OUTCOMES: Final[frozenset[VendorAttemptOutcome]] = frozenset(
    {VendorAttemptOutcome.RATE_LIMITED, VendorAttemptOutcome.CREDIT_REFUSAL}
)
SUCCESS_OUTCOMES: Final[frozenset[VendorAttemptOutcome]] = frozenset(
    {VendorAttemptOutcome.OK, VendorAttemptOutcome.SILENCE}
)
# Vendor-side failures that may fail over to another vendor (validated-empty is the existing
# Soniox second-chance precedent). Our-side failures (invalid payload, privacy) never fail over.
FAILOVER_OUTCOMES: Final[frozenset[VendorAttemptOutcome]] = frozenset(
    {
        VendorAttemptOutcome.ERROR_5XX,
        VendorAttemptOutcome.TIMEOUT,
        VendorAttemptOutcome.RATE_LIMITED,
        VendorAttemptOutcome.CREDIT_REFUSAL,
        VendorAttemptOutcome.EMPTY_VALIDATED,
        VendorAttemptOutcome.INVALID_RESPONSE,
        VendorAttemptOutcome.ABANDONED,
    }
)
# Job-document field holding the attempt list. ``provider_intent`` keeps its exact shape and
# always mirrors the current attempt, so a worker from before slice D still reconciles it.
ATTEMPTS_FIELD: Final = 'provider_attempts'


@dataclass(frozen=True)
class VendorAttempt:
    """One vendor call on one unit; ``provider_attempts[i]`` on the job document.

    Redelivery of an attempt reconciles only its own token's deterministic result object. A
    settled attempt never settles again: a late result for a settled non-success attempt is
    ignored and counted (``..._vendor_late_results_total{outcome='ignored'}``), never merged.
    """

    attempt: int  # 1-based, contiguous
    service: str  # a VENDOR_SERVICES member
    token: str
    privacy_generation: int | None
    started_at: float
    table_version: str
    outcome: VendorAttemptOutcome = VendorAttemptOutcome.RUNNING
    settled_at: float | None = None
    audio_seconds: float = 0.0  # duration sent to the vendor; 0 when no POST was made

    @property
    def billable(self) -> bool:
        if self.outcome is VendorAttemptOutcome.SILENCE:
            return self.audio_seconds > 0
        return self.outcome not in UNBILLED_OUTCOMES

    def to_dict(self) -> dict:
        return {
            'attempt': self.attempt,
            'service': self.service,
            'token': self.token,
            'privacy_generation': self.privacy_generation,
            'started_at': self.started_at,
            'table_version': self.table_version,
            'outcome': self.outcome.value,
            'settled_at': self.settled_at,
            'audio_seconds': self.audio_seconds,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> 'VendorAttempt':
        number, token = raw['attempt'], raw['token']
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= MAX_ATTEMPT_RECORDS:
            raise ValueError('bounded attempt number required')
        if raw['service'] not in VENDOR_SERVICES:
            raise ValueError('vendor service required')
        if not isinstance(token, str) or not token:
            raise ValueError('attempt token required')
        attempt = cls(
            attempt=number,
            service=raw['service'],
            token=token,
            privacy_generation=raw.get('privacy_generation'),
            started_at=raw['started_at'],
            table_version=raw['table_version'],
            outcome=VendorAttemptOutcome(raw['outcome']),
            settled_at=raw.get('settled_at'),
            audio_seconds=raw.get('audio_seconds', 0.0),
        )
        if (attempt.outcome is VendorAttemptOutcome.RUNNING) != (attempt.settled_at is None):
            raise ValueError('an attempt is running exactly when it is unsettled')
        if attempt.outcome is VendorAttemptOutcome.UNKNOWN:
            raise ValueError('closed attempt outcome required')
        return attempt


class AttemptRefused(ValueError):
    """``check_new_attempt`` refused a mint. Fixed messages; the stage defers or holds instead."""


def check_new_attempt(attempts: list[VendorAttempt], service: str) -> int:
    """Return the next attempt number for ``service`` or raise ``AttemptRefused``.

    Slice D calls this inside the same transaction as the CAS that mints the intent.
    """
    if service not in VENDOR_SERVICES:
        raise AttemptRefused('vendor service required')
    if [attempt.attempt for attempt in attempts] != list(range(1, len(attempts) + 1)):
        raise AttemptRefused('attempt records must be contiguous')
    if any(attempt.outcome is VendorAttemptOutcome.RUNNING for attempt in attempts):
        raise AttemptRefused('an attempt is still running')
    if any(attempt.outcome in SUCCESS_OUTCOMES for attempt in attempts):
        raise AttemptRefused('the unit already has a result')
    if any(attempt.outcome not in FAILOVER_OUTCOMES for attempt in attempts):
        raise AttemptRefused('a prior failure does not fail over')
    if len(attempts) >= MAX_ATTEMPT_RECORDS:
        raise AttemptRefused('attempt records exhausted')
    billable = [attempt for attempt in attempts if attempt.billable]
    if len(billable) >= MAX_BILLABLE_ATTEMPTS:
        raise AttemptRefused('billable attempts exhausted')
    if any(attempt.service == service for attempt in billable):
        raise AttemptRefused('this vendor was already paid for this unit')
    return len(attempts) + 1


# --- vendor_held (slice D implements) -------------------------------------------------------------

# Non-terminal parking for vendor outages. Contract:
# * Entered only when no permitted vendor is healthy *before* minting an intent: from
#   ``provider_pending``, or after a failed attempt that ``check_new_attempt`` would still allow
#   to fail over. Never with a running intent, never once attempts are exhausted (that stays
#   today's terminal ``quarantined`` + ``failed_held``).
# * Keeps ``merge_pending=True`` and the audio: owner order holds, nothing is lost or deleted.
# * Leaves to ``provider_pending`` (redrive; attempts preserved), to the GPU ring when GPU is
#   capable (rerouted), or to the existing privacy/supersede terminals. Auto-redrive fires when
#   any ``waiting_for`` service is allowed again, and at ``redrive_at`` regardless.
# * Guards: excluded from T3 wedge, the uncommitted-age proxy and the 2h no-terminal backstop
#   exactly like ``allowance_exhausted`` (``is_vendor_policy_hold``); never failed_held (T5),
#   never lost speech (T2), never our 5xx (T6). T1 custody applies unchanged. The exclusion
#   holds only while the hold is consistent and live: no running attempt, a redrive no further
#   out than the configured redrive interval, and not overdue by more than the stale grace.
#   Anything else (a dead redrive sweep, a far-future deadline, a held unit with a live intent)
#   surfaces as a wedge instead of hiding behind the exclusion.
VENDOR_HELD: Final = 'vendor_held'
HOLD_FIELD: Final = 'vendor_hold'


@dataclass(frozen=True)
class VendorHold:
    reason: VendorHoldReason
    held_at: float
    redrive_at: float
    redrives: int
    waiting_for: tuple[str, ...]  # vendor services whose recovery redrives the unit

    def to_dict(self) -> dict:
        return {
            'reason': self.reason.value,
            'held_at': self.held_at,
            'redrive_at': self.redrive_at,
            'redrives': self.redrives,
            'waiting_for': list(self.waiting_for),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> 'VendorHold':
        redrives = raw['redrives']
        if not isinstance(redrives, int) or isinstance(redrives, bool) or redrives < 0:
            raise ValueError('nonnegative redrive count required')
        hold = cls(
            reason=VendorHoldReason(raw['reason']),
            held_at=float(raw['held_at']),
            redrive_at=float(raw['redrive_at']),
            redrives=redrives,
            waiting_for=tuple(raw['waiting_for']),
        )
        if hold.reason is VendorHoldReason.UNKNOWN:
            raise ValueError('closed hold reason required')
        if not (math.isfinite(hold.held_at) and math.isfinite(hold.redrive_at)) or hold.redrive_at <= hold.held_at:
            raise ValueError('a hold always has a future redrive')
        if not hold.waiting_for or not set(hold.waiting_for) <= VENDOR_SERVICES:
            raise ValueError('a hold waits for at least one vendor service')
        return hold


def is_vendor_policy_hold(
    job: Mapping[str, Any], now: float, *, redrive_seconds: float, stale_grace_seconds: float
) -> bool:
    """True for a live, consistent ``vendor_held`` unit: guards exclude it like an allowance hold.

    ``redrive_seconds`` and ``stale_grace_seconds`` are the runtime values of
    ``BATCH_VENDOR_HELD_REDRIVE_SECONDS`` and ``BATCH_VENDOR_HELD_STALE_GRACE_SECONDS``.
    Malformed hold or attempt data is not a policy hold (the guard measures it).
    """
    if job.get('state') != VENDOR_HELD:
        return False
    raw_attempts = job.get(ATTEMPTS_FIELD, [])
    if not isinstance(raw_attempts, list):
        return False
    try:
        hold = VendorHold.from_dict(job[HOLD_FIELD])
        attempts = [VendorAttempt.from_dict(raw) for raw in raw_attempts]
    except (KeyError, TypeError, ValueError):
        return False
    # A live intent or a unit that already has a result is not waiting on a vendor.
    if any(
        attempt.outcome is VendorAttemptOutcome.RUNNING or attempt.outcome in SUCCESS_OUTCOMES for attempt in attempts
    ):
        return False
    return hold.redrive_at - now <= redrive_seconds and now <= hold.redrive_at + stale_grace_seconds


# --- rollout names (each slice fills only its own registry rows) ----------------------------------

# Nested in batch-pipeline (same empty salt, as batch-live-stt-retire): with the vendor percent
# at or below the batch percent, every vendor-routed owner is a batch owner (lockstep ramp).
VENDOR_ROUTING_COHORT: Final = 'batch-vendor-routing'
VENDOR_ROUTING_COHORT_SALT: Final = ''
# Independent salt: the GPU floor share is a stable owner bucket uncorrelated with the ramp.
GPU_FLOOR_COHORT: Final = 'batch-vendor-gpu-floor'
GPU_FLOOR_COHORT_SALT: Final = 'batch-vendor-gpu-floor'

# The complete new flag set. Defaults leave routing byte-identical to today.
FLAGS: Final[Mapping[str, tuple[str, str]]] = {
    # slice B
    'BATCH_VENDOR_ROUTING_ENABLED': ('B', 'ops_kill, on unless false; false serves BUILTIN_TABLE to everyone'),
    'BATCH_VENDOR_ROUTING_PERCENT': ('B', 'cohort percent of VENDOR_ROUTING_COHORT; default 0'),
    'BATCH_VENDOR_ROUTING_UID_ALLOWLIST': ('B', 'cohort allowlist; default empty'),
    'BATCH_VENDOR_ROUTING_SHADOW_PERCENT': ('B', 'decisions computed and counted, routing unchanged; default 0'),
    'BATCH_VENDOR_ROUTE_TABLE': ('B', 'runtime RouteTable payload; unset serves BUILTIN_TABLE'),
    # slice C
    'BATCH_VENDOR_HEALTH_ENABLED': ('C', 'ops_kill, on unless false; false keeps the process-local vendor_guard'),
    'BATCH_VENDOR_HEALTH_THRESHOLDS': ('C', 'runtime breaker thresholds (ops 1.4); unset keeps vendor_guard defaults'),
    # slice D
    'BATCH_VENDOR_FAILOVER_ENABLED': ('D', 'ops_kill, on unless false; false makes a failed attempt terminal'),
    'BATCH_VENDOR_HELD_REDRIVE_ENABLED': ('D', 'ops_kill, on unless false; false parks holds without redrive'),
    'BATCH_VENDOR_HELD_REDRIVE_SECONDS': ('D', 'runtime hold redrive interval'),
    'BATCH_VENDOR_HELD_STALE_GRACE_SECONDS': ('D', 'runtime grace past redrive_at before a hold counts as a wedge'),
}

# --- frozen metric names --------------------------------------------------------------------------
# Collectors and record helpers: utils.batch_pipeline.vendor_route_metrics (slices B, C and D
# import it; until then it has no serving importer by design).
# Prefix omi_batch_pipeline_ so the sync-fleet GMP keep-list and the rolling watcher already
# retain them: no keep-list edit, no BLIND window before the first vendor percent.

METRIC_ROUTE_DECISIONS: Final = 'omi_batch_pipeline_vendor_route_decisions_total'  # {route, reason}  B
METRIC_TABLE_LOADS: Final = 'omi_batch_pipeline_vendor_route_table_loads_total'  # {outcome}  B
METRIC_ATTEMPTS: Final = 'omi_batch_pipeline_vendor_attempts_total'  # {provider, outcome}  D
METRIC_ATTEMPT_AUDIO: Final = 'omi_batch_pipeline_vendor_attempt_audio_seconds_total'  # {provider, outcome}  D
METRIC_FAILOVERS: Final = 'omi_batch_pipeline_vendor_failovers_total'  # {from_route, to_route}  D
METRIC_LATE_RESULTS: Final = 'omi_batch_pipeline_vendor_late_results_total'  # {provider, outcome}  D
METRIC_PAID_INTENT_VIOLATIONS: Final = 'omi_batch_pipeline_vendor_paid_intent_violations_total'  # {provider}  D
METRIC_HOLD_TRANSITIONS: Final = 'omi_batch_pipeline_vendor_held_transitions_total'  # {outcome}  D
METRIC_HELD_UNITS: Final = 'omi_batch_pipeline_vendor_held_units'  # {reason}  D
METRIC_HELD_OLDEST_AGE: Final = 'omi_batch_pipeline_vendor_held_oldest_age_seconds'  # D
METRIC_HEALTH_DECISIONS: Final = 'omi_batch_pipeline_vendor_health_decisions_total'  # {provider, reason}  C
METRIC_BREAKER_STATE: Final = 'omi_batch_pipeline_vendor_breaker_state'  # {provider, state}  C
METRIC_AUDIO_HOURS_USED: Final = 'omi_batch_pipeline_vendor_audio_hours_used'  # {provider}  C
METRIC_AUDIO_HOURS_CAP: Final = 'omi_batch_pipeline_vendor_audio_hours_cap'  # {provider}  C
METRIC_CAP_HITS: Final = 'omi_batch_pipeline_vendor_cap_hits_total'  # {provider, reason}  C
BREAKER_STATES: Final[frozenset[str]] = frozenset({'closed', 'degraded', 'open', 'half_open'})
LATE_RESULT_OUTCOMES: Final[frozenset[str]] = frozenset({'ignored', 'reconciled'})
