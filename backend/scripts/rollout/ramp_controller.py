# LIFECYCLE: permanent
"""Ramp controller (contract (g)): a pure decision function plus a thin, host-agnostic runner.

Authority (contract (g)), enforced here and by tests:
- writes only envs.<env>.percents.{batch-pipeline, first-summary}; never legacy_sync, locked_by,
  batch-live-stt-retire, env vars, deploys, queues or scaling;
- acts only while legacy_sync == 'on'; refuses while locked_by is set or the prod-train lock is held;
- one ladder step per decision, at most one advance per 10 minutes (a rollback is never rate-limited:
  ROLLBACK_STOP_COUNT bounds repeats), never above 100, never skips;
- stops after two rollbacks in 24h until a human clears locked_by (a ramp_set --clear-lock write);
- never lowers a quality floor (QUALITY_FLOOR: first-summary); a rollback moves batch-pipeline only;
- before any ADVANCE, runs the serving-revision preflight (--preflight-cmd; required for prod --apply).

A --loop run pages the lead when it stops (signal, interrupt, exit) and after three consecutive failed ticks:
the ramp keeps its step (it already passed its gate, and a restart resumes) but nothing is watching it.

Host (decision S9): a supervised background process on m5 under the lead's prod-operator tier.
All ramp state lives in Firestore (`_ramp` + history), so a restart resumes from it. A local
heartbeat file records the last completed tick; if m5 slept or the process was down for longer
than --max-gap, the first tick after the gap only HOLDs (never advances blind) and posts that
it resumed; the next tick decides normally from a fresh gate observation.

The runner places no credentials. It uses whatever ADC the caller's GCP agent tier provides and
refuses --apply unless GCP_AGENT_TIER matches the environment (prod-operator / dev-operator).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field, replace
import datetime as dt
from enum import StrEnum
import json
import logging
import math
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Literal, Mapping, Sequence

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from database import rollout_cohorts as store  # noqa: E402
from utils.observability.reasons import RampReason  # noqa: E402
from utils.rollout.runtime_percent import RampSnapshot, clamp_nesting, write_ramp  # noqa: E402

logger = logging.getLogger('ramp_controller')

ACTOR = 'ramp-controller'
LADDER = (0.0, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0)
# Every step holds 1h. The 5% hold was 3h (David, 10-15); David's 10-20 ruling makes it 1h. There is
# no time-of-day requirement: waiting for daytime would stretch a night run into the next day.
HOLD_SECONDS = {5.0: 3600, 10.0: 3600, 25.0: 3600, 50.0: 3600, 75.0: 3600}
FIVE_PERCENT_STEP = 5.0
# Evidence, not clock: the 5% step also holds until the gate's `completed` count since the step began
# (batch units the client saw completed) reaches this floor. Measured 5% daytime traffic is ~225-430
# completions/hour; a quiet hour holds longer instead of failing.
FIVE_PERCENT_MIN_COMPLETED = 150
CONTROLLED_NAMES = ('batch-pipeline', 'first-summary')
LEAD_NAME = 'batch-pipeline'
# Quality guarantees, not ramp knobs: a rollback never lowers them. Every tested rollback set in the
# workspace's infra/rollout/ramp_env.json keeps FIRST_SUMMARY_DEADLINE_PERCENT=100 (prod's live value), and
# a rollback set that turned a recovery-quality flag off stranded 28 units in failed_held (2026-10-20).
# The value is the floor the operator CLI refuses to write below without --allow-quality-decrease.
QUALITY_FLOOR = {'first-summary': 100.0}
MIN_WRITE_INTERVAL_SECONDS = 600  # advances only; a rollback after a recent write acts at once
ROLLBACK_STOP_COUNT = 2
ROLLBACK_WINDOW_SECONDS = 24 * 3600
PROD_SHADOW_FROM_PERCENT = 25.0
HISTORY_SCAN_LIMIT = 400
STATE_FILE_DEFAULT = 'data/run-2026-10-13-two-lane-nemotron/STATE.md'
ANX_CARD_DEFAULT = 'two-lane-transcription-local-bench-quality-to-all-users'

# Fleet-gate data-loss and privacy tokens (contract (g)): ROLLBACK_ZERO.
DATA_LOSS_PREFIXES = ('terminal_unrecovered_speech_',)
DATA_LOSS_TOKENS = frozenset(
    {
        'stuck_job_over_30m',
        'obligation_over_15m',
        'projection_error',
        'projection_stalled',
        'failed_held_over_budget',  # settled failed_held quarantines are terminal recovery loss
        # A failed_held loss of unknown size must FAIL, never pass or hold (ramp runs 8-11: the gate's
        # threshold was mis-specified across five runs; lessons/batch-rollout-and-staging-traps.md #2).
        'failed_held_duration_unknown',
        'parity_row_5',
    }
)
PRIVACY_TOKENS = frozenset({'parity_row_7'})
# Ordinary cohort verdicts (fleet_gate.sh verdict(), plus composed parity): ROLLBACK_ONE. This is a closed
# list on purpose: every other GATE_FAIL token is a fleet_gate GateError (a read failed, a log page was
# truncated, a record had an unexpected shape, ro_dev/ro_prod credentials were missing) or a misinvocation,
# i.e. the gate could not judge the cohort. C1 ruling: those HOLD and escalate, never roll back.
COHORT_FAIL_TOKENS = frozenset(
    {
        'pre_existing_debt_growing',
        'projection_transient_rate',
        'unrecovered_quarantine',
        'recovery_spend_over_0_005_per_worn_hour',
        'recovery_spend_unknown',
        'quarantine_projection_p95_unknown',
        'quarantine_projection_p95_over_5m',
        'first_summary_dispatch_contract',
        'first_summary_completion_outlier',
        'first_summary_deadline',  # testing/pipeline_sim/scorer.py, the in-repo fleet_gate stand-in
        'http_5xx_regression',
        # P26 language-route verdicts (workspace fleet_gate 3172987): cohort audio routed to Parakeet in an
        # unknown/unsupported language, and completed units with no route evidence. Deliberate fail-closed
        # verdicts like recovery_spend_unknown, not gate read errors, so they roll back rather than hold.
        'unsafe_parakeet_language_route',
        'language_route_unknown',
        'parity_fail',
    }
)
COHORT_FAIL_PREFIXES = ('parity_row_',)
INCOMPLETE_SAMPLE_TOKENS = frozenset({'timeout_incomplete'})
# Preconditions for any env leaving legacy_sync='on' (contract (h) entry gate, plus lead/Subscription rulings).
# The controller never writes legacy_sync; ramp_set refuses `--legacy-sync draining|dark` until every id here is
# explicitly confirmed by the operator. Add an id when a ruling adds a gate; remove it only when the gate is retired.
DRAINING_PRECONDITIONS = {
    'cap_hold_ladder_debit': (
        'batch-admitted cap-hold units debit the ladder v1 usage budget (Subscription session ruling 10-19; '
        'lane 6 slice, tracked in swarm/status/lane06.md)'
    ),
    'minimal_redrive_finished': (
        "operator minimal-mode redrives (#22503) are finished or moved to the batch redrive path; draining stops "
        'new sequencer registration and legacy-retire C11 deletes the mode (lead ruling 10-20 05:17Z)'
    ),
    'provider_stt_live': (
        'C8 provider-STT is live in prod: the provider-stt Cloud Tasks queue exists, PROVIDER_STT_TASKS_* env is '
        'deployed, and the enrichment maintenance job (which also sweeps the provider-stt outbox) is scheduled; '
        'otherwise unsupported-language units strand in provider_pending (M3 GLM review, lead 43bd53)'
    ),
    'legacy_final_pass_rehomed': (
        'conversations still owned by legacy_final_pass_v1 with no live legacy job are re-homed to batch, so '
        'later uploads are not held on device after dark (M3 Luna review, lead ruling b209a5): the re-home '
        '(#23129) serves on every revision and scripts.legacy_dark.final_pass_rehome has sized the stock; its '
        '--apply runs in draining past the flip grace and must read CLEAR before dark'
    ),
}


class Action(StrEnum):
    ADVANCE = 'advance'
    HOLD = 'hold'
    ROLLBACK_ONE = 'rollback_one'
    ROLLBACK_ZERO = 'rollback_zero'


WRITE_ACTIONS = frozenset({Action.ADVANCE, Action.ROLLBACK_ONE, Action.ROLLBACK_ZERO})
ROLLBACK_ACTIONS = frozenset({Action.ROLLBACK_ONE, Action.ROLLBACK_ZERO})


@dataclass(frozen=True)
class GateVerdict:
    status: Literal['PASS', 'FAIL', 'NO_WORK', 'PENDING']
    reason: str  # the token after GATE_*, e.g. 'unrecovered_quarantine'
    observed_at: float
    hold_elapsed_seconds: float
    percent: float
    raw: Mapping[str, Any] = field(default_factory=dict)  # the gate's aggregate JSON, content-free


@dataclass(frozen=True)
class ControllerContext:
    """Facts the runner reads besides the snapshot. Defaults are the permissive, nothing-recent state."""

    seconds_since_last_controller_write: float = math.inf
    rollbacks_in_window: int = 0
    train_lock_held: bool = False
    hold_scale: float = 1.0  # staging rehearsal only; the runner refuses != 1.0 on prod
    resumed_after_gap: bool = False  # S9: first tick after sleep/restart never advances


@dataclass(frozen=True)
class Decision:
    action: Action
    name: str
    from_percent: float
    to_percent: float
    reason: RampReason
    detail: str = ''
    page: bool = False  # the lead must look (a FAIL the controller is not allowed to act on)


def next_step(current: float) -> float | None:
    return next((step for step in LADDER if step > current), None)


def previous_step(current: float) -> float:
    return max((step for step in LADDER if step < current), default=0.0)


def required_hold_seconds(current: float, hold_scale: float = 1.0) -> float:
    """The hold for the step the value sits on (an off-ladder value uses the step below it)."""
    base = max((step for step in HOLD_SECONDS if step <= current), default=None)
    return HOLD_SECONDS[base] * hold_scale if base is not None else 0.0


def five_percent_evidence_gap(verdict: GateVerdict, hold_scale: float = 1.0) -> str | None:
    """The 5% step's completion floor: the hold detail token while it is short, None once met.

    A missing or malformed `completed` count is short (fail closed). A staging rehearsal scales the
    floor by its hold_scale.
    """
    completed = verdict.raw.get('completed')
    if isinstance(completed, bool) or not isinstance(completed, int):
        return 'sample_unmeasured'
    if completed < math.ceil(FIVE_PERCENT_MIN_COMPLETED * hold_scale):
        return 'sample_below_floor'
    return None


def classify_fail(reason: str) -> tuple[Action | None, RampReason]:
    """Map a GATE_FAIL token to the rollback it requires; (None, ...) means HOLD (not a cohort verdict)."""
    if reason in INCOMPLETE_SAMPLE_TOKENS:
        return None, RampReason.GATE_PENDING
    if reason in PRIVACY_TOKENS:
        return Action.ROLLBACK_ZERO, RampReason.PRIVACY
    if reason in DATA_LOSS_TOKENS or reason.startswith(DATA_LOSS_PREFIXES):
        return Action.ROLLBACK_ZERO, RampReason.DATA_LOSS
    if reason in COHORT_FAIL_TOKENS or reason.startswith(COHORT_FAIL_PREFIXES):
        return Action.ROLLBACK_ONE, RampReason.GATE_FAIL
    return None, RampReason.GATE_FAIL


def decide(
    snapshot: RampSnapshot,
    verdict: GateVerdict,
    *,
    name: str,
    now: float,
    context: ControllerContext = ControllerContext(),
) -> Decision:
    """Pure decision for one controlled name. Writes nothing; the runner applies the result."""
    if name not in CONTROLLED_NAMES:
        raise ValueError('the controller never decides ' + name)
    current = snapshot.percents.get(name)

    def hold(reason: RampReason, detail: str, *, page: bool = False) -> Decision:
        value = current if current is not None else 0.0
        return Decision(Action.HOLD, name, value, value, reason, detail, page)

    is_fail = verdict.status == 'FAIL'
    if snapshot.source != 'firestore' or current is None:
        return hold(RampReason.LOCKED_BY_OPERATOR, 'not_seeded_or_unreadable', page=is_fail)
    if snapshot.legacy_sync != 'on':
        # A percent rollback cannot change admission in draining/dark (h); the lead's rollback is legacy_sync -> on.
        return hold(RampReason.LOCKED_BY_OPERATOR, 'legacy_sync_' + snapshot.legacy_sync, page=is_fail)
    if snapshot.locked_by is not None:
        return hold(RampReason.LOCKED_BY_OPERATOR, 'locked_by_set', page=is_fail)
    if context.train_lock_held:
        return hold(RampReason.LOCKED_BY_OPERATOR, 'prod_train_lock_held', page=is_fail)
    if context.rollbacks_in_window >= ROLLBACK_STOP_COUNT:
        return hold(RampReason.LOCKED_BY_OPERATOR, 'stopped_after_two_rollbacks', page=is_fail)
    if not math.isclose(verdict.percent, current, abs_tol=1e-9):
        return hold(RampReason.UNKNOWN, 'gate_percent_mismatch', page=is_fail)
    recent_write = context.seconds_since_last_controller_write < MIN_WRITE_INTERVAL_SECONDS
    if context.resumed_after_gap and not is_fail:
        # After sleep or restart, observe once before acting; a FAIL is still acted on (rollback is the safe side).
        return hold(RampReason.HOLD_INCOMPLETE, 'resume_after_gap')

    if is_fail:
        action, reason = classify_fail(verdict.reason)
        if action is None:
            return hold(reason, 'gate_fail_not_a_verdict:' + verdict.reason)
        if current <= 0.0:
            return hold(reason, 'at_floor', page=True)
        target = 0.0 if action is Action.ROLLBACK_ZERO else previous_step(current)
        # Not write-rate-limited: a FAIL minutes after an advance rolls back on this tick, not the next one.
        # ROLLBACK_STOP_COUNT (checked above) is what bounds repeated rollbacks.
        return Decision(action, name, current, target, reason, verdict.reason, page=action is Action.ROLLBACK_ZERO)
    if verdict.status in ('PENDING', 'NO_WORK'):
        return hold(RampReason.GATE_PENDING, verdict.status.lower())
    if verdict.status != 'PASS':
        return hold(RampReason.UNKNOWN, 'gate_status_unknown')
    if current >= 100.0:
        return hold(RampReason.AT_CEILING, 'at_100')
    if current <= 0.0:
        # From 0 (after ROLLBACK_ZERO or before seeding) a human re-seeds; the controller never restarts itself.
        return hold(RampReason.LOCKED_BY_OPERATOR, 'at_zero_needs_operator')
    if verdict.hold_elapsed_seconds < required_hold_seconds(current, context.hold_scale):
        return hold(RampReason.HOLD_INCOMPLETE, 'hold_incomplete')
    if FIVE_PERCENT_STEP <= current < next_step(FIVE_PERCENT_STEP):
        gap = five_percent_evidence_gap(verdict, context.hold_scale)
        if gap is not None:
            return hold(RampReason.HOLD_INCOMPLETE, gap)
    if recent_write:
        return hold(RampReason.HOLD_INCOMPLETE, 'write_rate_limited')
    target = next_step(current)
    if target is None or target > 100.0:
        return hold(RampReason.AT_CEILING, 'no_next_step')
    return Decision(Action.ADVANCE, name, current, target, RampReason.GATE_PASS, verdict.reason)


def decide_all(
    snapshot: RampSnapshot,
    verdict: GateVerdict,
    *,
    names: Sequence[str] = CONTROLLED_NAMES,
    now: float,
    context: ControllerContext = ControllerContext(),
) -> list[Decision]:
    """Decisions for every controlled name from one gate verdict. Followers advance only in lockstep with the
    lead; a quality-floor follower (QUALITY_FLOOR) is never lowered, and sitting above the lead is normal."""
    decisions = [decide(snapshot, verdict, name=name, now=now, context=context) for name in names]
    lead = next((item for item in decisions if item.name == LEAD_NAME), None)
    if lead is None:
        return decisions
    aligned = []
    for item in decisions:
        if item.name != LEAD_NAME:
            item = _align_follower(item, lead, snapshot.percents.get(item.name))
        aligned.append(item)
    return aligned


def _align_follower(item: Decision, lead: Decision, current: float | None) -> Decision:
    def hold(reason: RampReason, detail: str, page: bool = False) -> Decision:
        value = current if current is not None else 0.0
        return Decision(Action.HOLD, item.name, value, value, reason, detail, page)

    if item.name in QUALITY_FLOOR:
        if current is None:
            # Absent from `_ramp`, serving reads the env default (prod: 100). Writing the lead's value would lower it.
            return hold(lead.reason, 'quality_floor_unseeded')
        if lead.action in ROLLBACK_ACTIONS and current >= lead.from_percent:
            return hold(lead.reason, 'quality_floor_kept')
        if current > lead.from_percent:
            return hold(lead.reason, 'quality_floor_above_lead')
    if current is None or current != lead.from_percent:
        # A follower below (or, for a plain follower, off) the lead's value is an operator state; never let one
        # gate verdict move it.
        return hold(RampReason.UNKNOWN, 'follower_diverged', page=True)
    return item


# ---------------------------------------------------------------------------
# Runner: thin IO around decide(). Everything here is injectable for tests.
# ---------------------------------------------------------------------------


def iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def parse_iso(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def fmt_percent(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f'{value:g}'


def snapshot_from_document(document: Mapping[str, Any] | None, env: str) -> RampSnapshot:
    """Fresh, uncached snapshot for the controller (never the serving cache)."""
    entry = document['envs'].get(env) if document is not None else None
    if entry is None:
        return RampSnapshot(
            revision=document['revision'] if document is not None else 0,
            percents={},
            legacy_sync='on',
            locked_by=None,
            source='env_default',
            env=env,
        )
    return RampSnapshot(
        revision=document['revision'],
        percents=clamp_nesting(entry['percents']),
        legacy_sync=entry['legacy_sync'],
        locked_by=entry['locked_by'],
        source='firestore',
        env=env,
        updated_at=entry['updated_at'],
        updated_by=entry['updated_by'],
        reason=entry['reason'],
    )


@dataclass(frozen=True)
class HistoryFacts:
    hold_started_at: float | None
    last_controller_write_at: float | None
    rollbacks_in_window: int


def history_facts(rows: Sequence[Mapping[str, Any]], *, env: str, name: str, now: float) -> HistoryFacts:
    """Rows newest first. Rollbacks count only after the latest human locked_by clear (the acknowledgement)."""
    hold_started_at = last_write = None
    rollbacks = 0
    counting = True
    for row in rows:
        if row.get('env') != env:
            continue
        at = parse_iso(row.get('at'))
        before = row.get('before') or {}
        after = row.get('after') or {}
        actor = row.get('actor')
        if hold_started_at is None and (before.get('percents') or {}).get(name) != (after.get('percents') or {}).get(
            name
        ):
            hold_started_at = at
        if actor == ACTOR and last_write is None:
            last_write = at
        if (
            actor != ACTOR
            and 'locked_by' in after
            and after.get('locked_by') is None
            and row.get('reason') == 'lock_cleared'
        ):
            counting = False
        if counting and actor == ACTOR and row.get('reason') in ('gate_fail', 'data_loss', 'privacy'):
            if at is not None and now - at <= ROLLBACK_WINDOW_SECONDS:
                rollbacks += 1
    return HistoryFacts(hold_started_at, last_write, rollbacks)


_SAFE_TOKEN = re.compile(r'[A-Za-z0-9_.:+-]{1,64}')
GATE_EXIT = {0: 'PASS', 1: 'FAIL', 2: 'NO_WORK', 3: 'PENDING'}


def parse_gate_output(stdout: str, returncode: int) -> tuple[str, str, dict[str, Any]]:
    """fleet_gate.sh prints aggregate JSON lines, then one terminal `GATE_<STATUS> [reason]` line."""
    raw: dict[str, Any] = {}
    terminal = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                raw = value
        elif line.startswith('GATE_'):
            terminal = line
    if terminal is None:
        return 'FAIL', 'gate_output_unparsed', raw
    head, _, reason = terminal.partition(' ')
    status = head[len('GATE_') :]
    if status not in ('PASS', 'FAIL', 'NO_WORK', 'PENDING') or GATE_EXIT.get(returncode) != status:
        return 'FAIL', 'gate_output_unparsed', raw
    return status, reason.strip(), raw


def compact_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Only numeric/bool/short-token aggregates go into history and logs; never free text."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _SAFE_TOKEN.fullmatch(key):
            continue
        if isinstance(value, (bool, int, float)):
            out[key] = value
        elif isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
            out[key] = value
    return out


Runner = Callable[[Sequence[str], float], tuple[int, str]]


def run_command(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    try:
        completed = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return 124, 'GATE_FAIL gate_timeout'
    except OSError:
        return 127, 'GATE_FAIL gate_not_run'
    return completed.returncode, completed.stdout


def run_fleet_gate(
    gate_cmd: Sequence[str],
    *,
    since: float,
    min_completed: int,
    minutes: float,
    percent: float,
    runner: Runner,
    now: float,
) -> GateVerdict:
    argv = [*gate_cmd, iso(since), str(min_completed), fmt_percent(minutes), fmt_percent(percent)]
    code, stdout = runner(argv, minutes * 60 + 300)
    status, reason, raw = parse_gate_output(stdout, code)
    return GateVerdict(status, reason, now, max(0.0, now - since), percent, compact_raw(raw))  # type: ignore[arg-type]


def run_parity(parity_cmd: Sequence[str], *, runner: Runner, timeout: float = 1800) -> tuple[str, str]:
    """Lane 5 parity_gate.py --surface prod-shadow. Assumed: exit 0 PASS / 1 FAIL / 3 PENDING and a final
    `PARITY_<STATUS> <reason>` line, failing rows named `row_<n>` (issue C3 in the lane 6 status)."""
    code, stdout = runner(list(parity_cmd), timeout)
    terminal = next(
        (line.strip() for line in reversed(stdout.splitlines()) if line.strip().startswith('PARITY_')), None
    )
    if terminal is None:
        return 'FAIL', 'parity_not_run'
    head, _, reason = terminal.partition(' ')
    status = head[len('PARITY_') :]
    expected = {0: 'PASS', 1: 'FAIL', 3: 'PENDING'}.get(code)
    if status != expected:
        return 'FAIL', 'parity_not_run'
    return status, reason.strip()


def compose_with_parity(verdict: GateVerdict, parity: tuple[str, str] | None) -> GateVerdict:
    """From 25%, prod-shadow parity must PASS for ADVANCE; parity FAIL rolls back by the same rules."""
    if parity is None or verdict.status == 'FAIL':
        return verdict
    status, reason = parity
    if status == 'PASS':
        return replace(verdict, raw={**verdict.raw, 'prod_shadow': 'PASS'})
    if status == 'PENDING':
        return replace(
            verdict, status='PENDING', reason='parity_pending', raw={**verdict.raw, 'prod_shadow': 'PENDING'}
        )
    if reason == 'parity_not_run':
        return replace(verdict, status='FAIL', reason='parity_not_run')
    token = 'parity_' + reason if reason.startswith('row_') else 'parity_fail'
    return replace(verdict, status='FAIL', reason=token, raw={**verdict.raw, 'prod_shadow': 'FAIL'})


def state_line(decision: Decision, verdict: GateVerdict, revision: int | None, at: float) -> str:
    return (
        f'{iso(at)} ramp-controller {decision.name} {decision.action.value} '
        f'{fmt_percent(decision.from_percent)}→{fmt_percent(decision.to_percent)} '
        f'reason={decision.reason.value} gate={verdict.status}:{verdict.reason or "-"} rev={revision if revision is not None else "-"}'
    )


@dataclass
class Effects:
    """Side-effect ports. Production binds Firestore, the gate scripts, STATE.md and anx; tests bind fakes."""

    read_document: Callable[[], Mapping[str, Any] | None]
    read_history: Callable[[Sequence[int]], list[Mapping[str, Any]]]
    write: Callable[..., int]
    gate: Callable[[float, float], GateVerdict]  # (since, percent) -> verdict
    parity: Callable[[], tuple[str, str]] | None
    train_lock_held: Callable[[], bool]
    append_state: Callable[[str], None]
    notify: Callable[[str, bool], None]  # (text, page)
    clock: Callable[[], float] = time.time
    # Serving-revision preflight, consulted only before an ADVANCE (never blocks a rollback): (percent) ->
    # (ok, token). Prod --apply requires it (ramp5.sh's lesson: check the revision that serves, not the source).
    preflight: Callable[[float], tuple[bool, str]] | None = None


@dataclass
class TickResult:
    decisions: list[Decision]
    verdict: GateVerdict | None
    revision: int | None
    wrote: bool


def tick(
    env: str,
    effects: Effects,
    *,
    names: Sequence[str] = CONTROLLED_NAMES,
    hold_scale: float = 1.0,
    apply: bool = True,
    require_parity: bool | None = None,
    resumed_after_gap: bool = False,
) -> TickResult:
    """One controller pass: read, gate, decide, write (at most once), log."""
    now = effects.clock()
    if require_parity is None:
        require_parity = env == 'prod'
    document = effects.read_document()
    snapshot = snapshot_from_document(document, env)
    revision = snapshot.revision or 0
    rows = effects.read_history(range(revision, max(0, revision - HISTORY_SCAN_LIMIT), -1)) if revision else []
    facts = history_facts(rows, env=env, name=LEAD_NAME, now=now)
    current = snapshot.percents.get(LEAD_NAME)
    since = facts.hold_started_at or parse_iso(snapshot.updated_at) or now
    since = min(since, now)
    if current is None or snapshot.source != 'firestore':
        verdict = GateVerdict('PENDING', 'not_seeded', now, 0.0, 0.0, {})
    else:
        verdict = effects.gate(since, current)
        verdict = replace(verdict, hold_elapsed_seconds=max(0.0, now - since), observed_at=now)
        if current >= PROD_SHADOW_FROM_PERCENT and effects.parity is not None and verdict.status != 'FAIL':
            verdict = compose_with_parity(verdict, effects.parity())
        elif (
            current >= PROD_SHADOW_FROM_PERCENT
            and require_parity
            and effects.parity is None
            and verdict.status == 'PASS'
        ):
            verdict = replace(verdict, status='PENDING', reason='parity_not_configured')
    context = ControllerContext(
        seconds_since_last_controller_write=(
            (now - facts.last_controller_write_at) if facts.last_controller_write_at is not None else math.inf
        ),
        rollbacks_in_window=facts.rollbacks_in_window,
        train_lock_held=effects.train_lock_held(),
        hold_scale=hold_scale,
        resumed_after_gap=resumed_after_gap,
    )
    decisions = decide_all(snapshot, verdict, names=names, now=now, context=context)
    if effects.preflight is not None and any(item.action is Action.ADVANCE for item in decisions):
        ok, token = effects.preflight(current if current is not None else 0.0)
        if not ok:
            decisions = [
                (
                    Decision(
                        Action.HOLD,
                        item.name,
                        item.from_percent,
                        item.from_percent,
                        RampReason.HOLD_INCOMPLETE,
                        'preflight:' + token,
                        item.name == LEAD_NAME,
                    )
                    if item.action is Action.ADVANCE
                    else item
                )
                for item in decisions
            ]
    writes = [item for item in decisions if item.action in WRITE_ACTIONS]
    new_revision = snapshot.revision
    wrote = False
    if writes and apply:
        lead = next((item for item in writes if item.name == LEAD_NAME), writes[0])
        change = {'percents': {item.name: item.to_percent for item in writes}}
        try:
            new_revision = effects.write(
                env,
                change,
                expected_revision=revision,
                actor=ACTOR,
                reason=lead.reason.value,
                gate_verdict={
                    'status': verdict.status,
                    'reason': verdict.reason,
                    'percent': verdict.percent,
                    **dict(verdict.raw),
                },
            )
            wrote = True
        except store.RampRevisionConflict:
            decisions = [
                (
                    Decision(
                        Action.HOLD, item.name, item.from_percent, item.from_percent, RampReason.UNKNOWN, 'cas_conflict'
                    )
                    if item.action in WRITE_ACTIONS
                    else item
                )
                for item in decisions
            ]
    for item in decisions:
        effects.append_state(state_line(item, verdict, new_revision, now) + ('' if apply else ' dry_run=1'))
    for item in decisions:
        if (wrote and item.action in WRITE_ACTIONS) or item.page or item.detail == 'resume_after_gap':
            text = (
                f'ramp-controller {env} {item.name} {item.action.value} {fmt_percent(item.from_percent)}→'
                f'{fmt_percent(item.to_percent)} reason={item.reason.value} gate={verdict.status}:{verdict.reason or "-"} '
                f'detail={item.detail or "-"} rev={new_revision}'
            )
            effects.notify(('PAGE lead: ' if item.page else '') + text, item.page)
    return TickResult(decisions, verdict, new_revision, wrote)


UNAVAILABLE_ESCALATE_TICKS = 3  # C1 ruling: escalate a gate that cannot run for 3 consecutive ticks (~30 min)


def gate_unavailable(verdict: GateVerdict | None) -> bool:
    """The gate (or prod-shadow parity) could not produce a cohort verdict; the controller holds (C1)."""
    if verdict is None or verdict.status != 'FAIL':
        return False
    action, _ = classify_fail(verdict.reason)
    return action is None


def next_unavailable_streak(previous: int, verdict: GateVerdict | None) -> int:
    return previous + 1 if gate_unavailable(verdict) else 0


def should_escalate_unavailable(streak: int) -> bool:
    return streak >= UNAVAILABLE_ESCALATE_TICKS and streak % UNAVAILABLE_ESCALATE_TICKS == 0


def read_heartbeat(path: Path) -> tuple[float | None, int]:
    """(last completed tick, consecutive gate-unavailable ticks); a missing/garbled file is (None, 0)."""
    try:
        parts = path.read_text(encoding='utf-8').split()
        at = float(parts[0])
        streak = int(parts[1]) if len(parts) > 1 else 0
    except (OSError, ValueError, IndexError):
        return None, 0
    return (at if math.isfinite(at) else None), max(0, streak)


def write_heartbeat(path: Path, at: float, unavailable_streak: int = 0) -> None:
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(f'{at:.3f} {unavailable_streak}\n', encoding='utf-8')
    tmp.replace(path)


def append_line(path: Path, line: str) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def anx_notify(card: str, runner: Runner) -> Callable[[str, bool], None]:
    def notify(text: str, page: bool) -> None:
        code, _ = runner(['anx', 'note', card, text], 60)
        if code != 0:
            logger.warning('event=ramp_controller_notify outcome=failed page=%s', page)

    return notify


def train_lock_probe(cmd: Sequence[str] | None, runner: Runner) -> Callable[[], bool]:
    """B5 `prod-train` lock: exit 0 = free, 1 = held; anything else is treated as held (fail closed)."""

    def held() -> bool:
        if not cmd:
            return False
        code, _ = runner(list(cmd), 120)
        return code != 0

    return held


PREFLIGHT_TIMEOUT_SECONDS = 900


def preflight_probe(cmd: Sequence[str], runner: Runner) -> Callable[[float], tuple[bool, str]]:
    """`<cmd> <current percent>`: exit 0 = the serving revisions and backlog allow an ADVANCE. Anything else
    holds (fail closed); the last output line, when it is a short token, names the reason."""

    def check(percent: float) -> tuple[bool, str]:
        code, stdout = runner([*cmd, fmt_percent(percent)], PREFLIGHT_TIMEOUT_SECONDS)
        if code == 0:
            return True, 'ok'
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        last = lines[-1].split()[-1] if lines else ''
        return False, last if _SAFE_TOKEN.fullmatch(last) else 'preflight_failed'

    return check


def stop_notice(env: str, cause: str, last_percent: float | None) -> str:
    at = fmt_percent(last_percent) if last_percent is not None else 'unknown'
    return (
        f'PAGE lead: ramp-controller {env} stopped ({cause}) at batch-pipeline={at}%. The ramp stays at that step '
        f'with no gate watching it: restart the controller, or lock it with ramp_set --lock'
    )


EXPECTED_TIER = {'prod': 'prod-operator', 'staging': 'dev-operator'}
DEFAULT_TARGET = {'prod': ('based-hardware', '(default)'), 'staging': ('based-hardware-dev', 'staging')}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env', choices=sorted(EXPECTED_TIER), required=True)
    parser.add_argument('--project', help='Firestore project (default per env)')
    parser.add_argument('--database', help='Firestore database id (default per env)')
    parser.add_argument('--gate-cmd', required=True, help='Fleet gate command prefix, e.g. ".../ops/fleet_gate.sh"')
    parser.add_argument('--min-completed', type=int, default=1)
    parser.add_argument('--gate-minutes', type=float, default=15.0)
    parser.add_argument('--parity-cmd', help='Prod-shadow parity command (required from 25%% on prod)')
    parser.add_argument('--train-lock-cmd', help='B5 prod-train lock probe: exit 0 free, 1 held')
    parser.add_argument(
        '--preflight-cmd',
        help='Serving-revision preflight run before any ADVANCE with the current percent appended; exit 0 = ok '
        '(prod: the workspace infra/rollout/bin/controller_preflight.sh)',
    )
    parser.add_argument('--state-file', default=STATE_FILE_DEFAULT)
    parser.add_argument('--anx-card', default=ANX_CARD_DEFAULT)
    parser.add_argument('--no-anx', action='store_true', help='Skip anx notes (rehearsal on a host without anx)')
    parser.add_argument('--hold-scale', type=float, default=1.0, help='Staging rehearsal only')
    parser.add_argument('--interval', type=float, default=600.0, help='Seconds between ticks in --loop mode')
    parser.add_argument('--loop', action='store_true', help='Tick until interrupted (else one tick)')
    parser.add_argument('--heartbeat-file', help='Local last-tick file (S9 resume guard); default beside --state-file')
    parser.add_argument('--max-gap', type=float, default=1800.0, help='Seconds without a tick that count as a pause')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Decide and log, never write (default)')
    mode.add_argument('--apply', action='store_true', help='Write `_ramp` percents on the matching operator tier')
    return parser


def validate_args(args: argparse.Namespace) -> str | None:
    if args.env == 'prod':
        if args.hold_scale != 1.0:
            return 'hold_scale_is_staging_only'
        if 'inject_gate' in (args.gate_cmd or ''):
            return 'injected_gate_is_staging_only'
        if args.apply and not args.train_lock_cmd:
            return 'prod_apply_requires_train_lock_cmd'
        if args.apply and not args.parity_cmd:
            return 'prod_apply_requires_parity_cmd'
        if args.apply and not args.preflight_cmd:
            return 'prod_apply_requires_preflight_cmd'
    if not 0 < args.hold_scale <= 1.0 or not math.isfinite(args.hold_scale):
        return 'hold_scale_out_of_range'
    if args.apply and os.getenv('GCP_AGENT_TIER') != EXPECTED_TIER[args.env]:
        return 'operator_tier_mismatch'
    return None


def main(
    argv: Sequence[str] | None = None, *, client_factory: Callable[..., Any] | None = None, runner: Runner = run_command
) -> int:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    args = build_parser().parse_args(argv)
    problem = validate_args(args)
    if problem:
        print('ramp_controller refused: ' + problem, file=sys.stderr)
        return 2
    project, database = DEFAULT_TARGET[args.env]
    project, database = args.project or project, args.database or database
    if client_factory is None:
        client_factory = firestore.Client
    client = client_factory(project=project, database=database)
    gate_cmd = shlex.split(args.gate_cmd)
    parity_cmd = shlex.split(args.parity_cmd) if args.parity_cmd else None
    state_path = Path(args.state_file)
    effects = Effects(
        read_document=lambda: store.read_ramp(firestore_client=client, timeout=store.OPERATOR_READ_TIMEOUT_SECONDS),
        read_history=lambda revisions: store.read_ramp_history(revisions, firestore_client=client),
        write=lambda env, change, **kw: write_ramp(env, change, firestore_client=client, **kw),
        gate=lambda since, percent: run_fleet_gate(
            gate_cmd,
            since=since,
            min_completed=args.min_completed,
            minutes=args.gate_minutes,
            percent=percent,
            runner=runner,
            now=time.time(),
        ),
        parity=(lambda: run_parity(parity_cmd, runner=runner)) if parity_cmd else None,
        train_lock_held=train_lock_probe(shlex.split(args.train_lock_cmd) if args.train_lock_cmd else None, runner),
        append_state=lambda line: append_line(state_path, line),
        notify=(lambda text, page: None) if args.no_anx else anx_notify(args.anx_card, runner),
        preflight=preflight_probe(shlex.split(args.preflight_cmd), runner) if args.preflight_cmd else None,
    )
    heartbeat = (
        Path(args.heartbeat_file)
        if args.heartbeat_file
        else state_path.with_name(f'.ramp_controller_{args.env}.heartbeat')
    )
    if not args.loop:
        return _one_tick(args, effects, heartbeat)
    # A stopped loop leaves the ramp at its step with no gate watching (ramp5.sh rolled back on exit; the
    # controller keeps the step, since it already passed its gate and a restart resumes, but it must say so).
    previous = {sig: signal.signal(sig, _raise_stop) for sig in (signal.SIGTERM, signal.SIGHUP)}
    cause, last_percent, errors = 'exit', None, 0
    try:
        while True:
            try:
                result = _tick_once(args, effects, heartbeat)
                errors = 0
                lead = next((item for item in result.decisions if item.name == LEAD_NAME), None)
                last_percent = lead.to_percent if lead is not None else last_percent
            except Exception as error:  # noqa: BLE001 - a failed tick writes nothing; log the class only
                errors += 1
                logger.warning('event=ramp_controller_tick outcome=error error=%s', type(error).__name__)
                if args.apply and should_escalate_unavailable(errors):
                    try:
                        effects.notify(
                            f'PAGE lead: ramp-controller {args.env} tick failed {errors} consecutive times '
                            f'({type(error).__name__}); the ramp is unsupervised at its current step',
                            True,
                        )
                    except Exception:  # noqa: BLE001 - a failed page must not end the loop
                        logger.warning('event=ramp_controller_error_page outcome=failed')
            _sleep(args.interval)
    except KeyboardInterrupt:
        cause = 'interrupted'
        return 130
    except _Stop as stop:
        cause = 'signal_' + signal.Signals(stop.signum).name
        return 128 + stop.signum
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if args.apply:  # a dry-run loop supervises nothing
            try:
                effects.notify(stop_notice(args.env, cause, last_percent), True)
            except Exception:  # noqa: BLE001 - best effort on the way out
                logger.warning('event=ramp_controller_stop_notice outcome=failed')


class _Stop(BaseException):
    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def _raise_stop(signum: int, _frame: Any) -> None:
    raise _Stop(signum)


_sleep = time.sleep  # tests replace it


def _tick_once(args: argparse.Namespace, effects: Effects, heartbeat: Path) -> TickResult:
    last, streak = read_heartbeat(heartbeat)
    gap = last is None or time.time() - last > args.max_gap
    result = tick(args.env, effects, hold_scale=args.hold_scale, apply=args.apply, resumed_after_gap=gap)
    # The streak survives a restart (it is in the heartbeat file) but a pause gap resets it.
    streak = next_unavailable_streak(0 if gap else streak, result.verdict)
    if should_escalate_unavailable(streak) and result.verdict is not None:
        effects.notify(
            f'PAGE lead: ramp-controller {args.env} gate unavailable for {streak} consecutive ticks '
            f'(gate={result.verdict.status}:{result.verdict.reason}); holding at the current step',
            True,
        )
    write_heartbeat(heartbeat, time.time(), streak)
    print(
        json.dumps(
            {
                'decisions': [asdict(item) for item in result.decisions],
                'revision': result.revision,
                'wrote': result.wrote,
            },
            default=str,
        )
    )
    return result


def _one_tick(args: argparse.Namespace, effects: Effects, heartbeat: Path) -> int:
    try:
        _tick_once(args, effects, heartbeat)
    except Exception as error:  # noqa: BLE001 - a failed tick writes nothing; log the class only
        logger.warning('event=ramp_controller_tick outcome=error error=%s', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
