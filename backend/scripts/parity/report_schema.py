"""Report schema for the legacy-retirement parity gate (contract (j)).

Pure data: no IO, no clients. ``parity_gate.py`` writes ``parity_report.json``
in this shape; ``soak_check.py`` reuses the verdict vocabulary. Thresholds are
frozen by contract (j): change them only through the M1 review with measured
baseline noise and captain plus lead sign-off.

Every value that crosses the report boundary is an aggregate (counts, rates,
seconds, dollars) or a fixed reason token. Never put uids, content ids,
conversation ids, transcript text or exception strings in a report.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping

SCHEMA_VERSION = 1


class Surface(StrEnum):
    STAGING = 'staging'
    PROD_SHADOW = 'prod-shadow'


class Status(StrEnum):
    PASS = 'PASS'
    FAIL = 'FAIL'
    PENDING = 'PENDING'
    # A row that is not evaluated on this surface (contract (j) "Surface" column).
    NOT_APPLICABLE = 'N/A'


class ParityReason(StrEnum):
    """Content-free reasons, family ``parity`` in contract (e).

    Lane 14 may hoist this class into ``utils/observability/reasons.py``; the
    values are the contract and must not change when it moves.
    """

    UNKNOWN = 'unknown'
    PASS = 'pass'
    SAMPLE_BELOW_MINIMUM = 'sample_below_minimum'
    INPUT_MISSING = 'input_missing'
    INPUT_INVALID = 'input_invalid'
    WER_DELTA_OVER_LIMIT = 'wer_delta_over_limit'
    AGREEMENT_MEDIAN_OVER_LIMIT = 'agreement_median_over_limit'
    AGREEMENT_OUTLIER_UNREVIEWED = 'agreement_outlier_unreviewed'
    SPEAKER_ACCURACY_REGRESSED = 'speaker_accuracy_regressed'
    OWNER_AGREEMENT_BELOW_LIMIT = 'owner_agreement_below_limit'
    FIRST_SUMMARY_DISPATCH_BREACH = 'first_summary_dispatch_breach'
    FIRST_SUMMARY_COMPLETION_P95 = 'first_summary_completion_p95'
    ACCEPT_TO_SUMMARY_P95 = 'accept_to_summary_p95'
    STUCK_JOB_OVER_30M = 'stuck_job_over_30m'
    OBLIGATION_OVER_15M = 'obligation_over_15m'
    TERMINAL_UNRECOVERED_SPEECH = 'terminal_unrecovered_speech'
    COUNT_DRIFT = 'count_drift'
    DURATION_DRIFT = 'duration_drift'
    LOST_RECORDINGS = 'lost_recordings'
    COST_ABOVE_LEGACY = 'cost_above_legacy'
    THROUGHPUT_BELOW_FLOOR = 'throughput_below_floor'
    PRIVACY_VIOLATION = 'privacy_violation'
    ORDERING_VIOLATION = 'ordering_violation'


# Rows whose non-zero FAIL is data loss or privacy: contract (g) maps these to
# ROLLBACK_ZERO. Everything else rolls back one step.
DATA_LOSS_ROWS = frozenset({'5', '7'})
DATA_LOSS_REASONS = frozenset({ParityReason.LOST_RECORDINGS, ParityReason.PRIVACY_VIOLATION})

# Contract (j) surfaces per row. 'both' rows must pass on each listed surface.
ROW_SURFACES: Mapping[str, frozenset[Surface]] = {
    '1': frozenset({Surface.STAGING}),
    # Prod shadow: David's own recordings via the mirror (replay half only); reported, never gating.
    '1b': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '2': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '3': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '4': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '5': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '6': frozenset({Surface.STAGING, Surface.PROD_SHADOW}),
    '7': frozenset({Surface.STAGING}),
    '8': frozenset({Surface.STAGING}),
}
# The prod-shadow verdict that gates ladder ADVANCE uses rows 3-6 only (contract (g)).
PROD_SHADOW_GATING_ROWS = ('3', '4', '5', '6')
ROW_TITLES = {
    '1': 'transcript_accuracy',
    '1b': 'transcript_agreement',
    '2': 'speaker_labels',
    '3': 'first_summary_latency',
    '4': 'completeness',
    '5': 'zero_lost_recordings',
    '6': 'cost_per_audio_hour',
    '7': 'privacy',
    '8': 'ordering',
}


@dataclass(frozen=True)
class Thresholds:
    """Frozen contract (j) thresholds."""

    wer_delta_pp: float = 0.5
    wer_min_corpus_minutes: float = 60.0
    agreement_median_max: float = 0.08
    agreement_outlier_max: float = 0.25
    agreement_min_conversations: int = 200
    speaker_accuracy_drop_pp: float = 1.0
    owner_agreement_min: float = 0.97
    owner_agreement_min_conversations: int = 200
    first_summary_dispatch_limit_seconds: float = 121.0
    first_summary_min_dispatches: int = 20
    first_summary_completion_p95_seconds: float = 300.0
    accept_to_summary_p95_slack_seconds: float = 60.0
    stuck_job_seconds: float = 1800.0
    terminal_unrecovered_speech_max: float = 0.002
    count_duration_tolerance: float = 0.01
    cost_min_steady_hours: float = 2.0
    leases_per_min_per_node_floor: float = 45.0
    max_nodes: int = 4
    legacy_leases_per_min_mean: float = 174.0


THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class RowResult:
    row: str
    status: Status
    reason: ParityReason
    surface: Surface
    measured: Mapping[str, Any] = field(default_factory=dict)
    sample: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            'row': self.row,
            'title': ROW_TITLES[self.row],
            'status': self.status.value,
            'reason': self.reason.value,
            'surface': self.surface.value,
            'measured': dict(self.measured),
            'sample': dict(self.sample),
        }


@dataclass(frozen=True)
class ParityReport:
    surface: Surface
    status: Status
    reason: ParityReason
    rows: tuple[RowResult, ...]
    generated_at: str
    window: Mapping[str, Any]
    inputs: Mapping[str, Any]
    data_loss: bool
    # Ramp percent the measured throughput carries (contract (j) throughput precondition).
    max_supported_percent: float | None = None
    # The row a FAIL is named after on the terminal line (contract (j) "FAIL reason").
    failing_row: str | None = None

    def terminal_reason(self) -> str:
        """``row_<n>`` for a FAIL (the controller keys ROLLBACK_ZERO on rows 5 and 7); else the reason."""
        if self.status is Status.FAIL and self.failing_row is not None:
            return f'row_{self.failing_row}'
        return self.reason.value

    def to_json(self) -> dict[str, Any]:
        return {
            'schema_version': SCHEMA_VERSION,
            'surface': self.surface.value,
            'status': self.status.value,
            'reason': self.reason.value,
            'failing_row': self.failing_row,
            'data_loss': self.data_loss,
            'max_supported_percent': self.max_supported_percent,
            'generated_at': self.generated_at,
            'window': dict(self.window),
            'inputs': dict(self.inputs),
            'thresholds': asdict(THRESHOLDS),
            'rows': [row.to_json() for row in self.rows],
        }


EXIT_CODES = {Status.PASS: 0, Status.FAIL: 1, Status.PENDING: 3}


def verdict_line(prefix: str, status: Status, reason: ParityReason | str) -> str:
    """``PARITY_PASS`` / ``PARITY_FAIL <reason>`` / ``PARITY_PENDING <reason>``.

    Same shape as the fleet gate's last line so the ramp controller parses both
    the same way.
    """
    if status is Status.PASS:
        return prefix + '_PASS'
    return f'{prefix}_{status.value} {reason}'


def combine(rows: list[RowResult], surface: Surface, gating_rows: tuple[str, ...] | None = None):
    """Report-level status: any FAIL fails; else any PENDING pends; else PASS.

    Returns ``(status, reason, data_loss, failing_row)``. A data-loss FAIL (row 5,
    then row 7) takes precedence over every other FAIL so the controller rolls
    back to zero; otherwise the lowest failing row (``rows`` is in row order).
    """
    considered = [r for r in rows if r.status is not Status.NOT_APPLICABLE]
    if gating_rows is not None:
        considered = [r for r in considered if r.row in gating_rows]
    failed = [r for r in considered if r.status is Status.FAIL]
    if failed:
        loss = [r for r in failed if r.row in DATA_LOSS_ROWS or r.reason in DATA_LOSS_REASONS]
        first = loss[0] if loss else failed[0]
        return Status.FAIL, first.reason, bool(loss), first.row
    pending = [r for r in considered if r.status is Status.PENDING]
    if pending:
        return Status.PENDING, pending[0].reason, False, None
    if not considered:
        return Status.PENDING, ParityReason.INPUT_MISSING, False, None
    return Status.PASS, ParityReason.PASS, False, None
