"""Session-counted binary gate. Pure transitions are also used by Redis CAS."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from typing import Any

# 10x 1,800 sessions/hour is 1,500 identities per five-minute window.
HEALTHY_USERS = 2048
FAILURE_RESERVE = 8


@dataclass(frozen=True)
class GateState:
    threshold: float = 0.08
    stage: int = 100
    n: int = 0
    failures: int = 0
    evidence: tuple[float, ...] = (0.0, 0.0, 0.0)
    until: float = 0
    strikes: int = 0
    generation: int = 0
    trial_started_at: float = 0.0
    witnesses: tuple[str, ...] = ()
    recent_failures: tuple[str, ...] = ()
    trial_users: tuple[tuple[str, int, int], ...] = ()
    healthy_window: int = -1
    healthy_users: tuple[tuple[str, int], ...] = ()
    overflow_failures: tuple[str, ...] = ()

    @classmethod
    def decode(cls, raw: dict[str, Any]) -> GateState:
        raw = dict(raw)
        if not all(type(raw.get(field, 0)) is int for field in ('n', 'failures', 'generation', 'strikes', 'stage')):
            raise ValueError('invalid cost gate counts')
        raw['evidence'] = tuple(raw.get('evidence', cls().evidence))
        users = raw.get('trial_users', ())
        if not isinstance(users, (list, tuple)) or len(users) > 240:
            raise ValueError('invalid trial users')
        for user in users:
            if (
                not isinstance(user, (list, tuple))
                or len(user) != 3
                or not isinstance(user[0], str)
                or len(user[0]) != 16
                or type(user[1]) is not int
                or type(user[2]) is not int
                or not 0 <= user[2] <= user[1] <= 3
                or user[1] == 0
            ):
                raise ValueError('invalid trial user vote')
        raw['trial_users'] = tuple(tuple(user) for user in users)
        if len({user[0] for user in users}) != len(users):
            raise ValueError('duplicate trial user')
        healthy = raw.get('healthy_users', ())
        if (
            type(raw.get('healthy_window', -1)) is not int
            or raw.get('healthy_window', -1) < -1
            or not isinstance(healthy, (list, tuple))
            or len(healthy) > HEALTHY_USERS
        ):
            raise ValueError('invalid healthy evidence window')
        for user in healthy:
            if (
                not isinstance(user, (list, tuple))
                or len(user) != 2
                or not isinstance(user[0], str)
                or len(user[0]) != 16
                or type(user[1]) is not int
                or not 1 <= user[1] <= 3
            ):
                raise ValueError('invalid healthy user budget')
        if len({user[0] for user in healthy}) != len(healthy):
            raise ValueError('duplicate healthy user')
        raw['healthy_users'] = tuple(tuple(user) for user in healthy)
        for field in ('witnesses', 'recent_failures', 'overflow_failures'):
            values: list[Any] = list(raw.get(field, ()))
            if any(
                not isinstance(value, str) or (len(value) != 16 and not (field == 'recent_failures' and value == ''))
                for value in values
            ):
                raise ValueError('invalid cost gate witnesses')
            raw[field] = tuple(values)
        if type(raw.get('trial_started_at', 0.0)) not in (int, float):
            raise ValueError('invalid trial start')
        state = cls(**raw)
        if (
            not math.isfinite(state.threshold)
            or not 0 < state.threshold < 1
            or state.stage not in (0, 5, 25, 100)
            or not 0 <= state.failures <= state.n <= 1_000_000
            or len(state.evidence) != 3
            or not all(math.isfinite(value) and 0 <= value <= 1000 for value in state.evidence)
            or not math.isfinite(state.until)
            or state.until < 0
            or not math.isfinite(state.trial_started_at)
            or state.trial_started_at < 0
            or state.generation < 0
            or not 0 <= state.strikes <= 10
            or len(state.witnesses) > 4
            or len(set(state.witnesses)) != len(state.witnesses)
            or len(state.overflow_failures) > FAILURE_RESERVE
            or len(set(state.overflow_failures)) != len(state.overflow_failures)
            or len(state.recent_failures) > 32
        ):
            raise ValueError('invalid cost gate state')
        return state

    def encode(self) -> dict[str, Any]:
        return asdict(self)


def gate_rate() -> float:
    gate = float(os.getenv('STT_ROUTING_DISRUPTION_GATE', '0.08'))
    if not math.isfinite(gate) or not 0 < gate < 1:
        raise ValueError('disruption gate must be between 0 and 1')
    return gate


@lru_cache(maxsize=16)
def _increments(gate: float) -> tuple[tuple[float, float], ...]:
    # At the default gate these alternatives are 12%, 16%, and 60%.
    return tuple(
        (math.log(q / gate), math.log((1 - q) / (1 - gate)))
        for q in (gate + (1 - gate) * fraction for fraction in (1 / 23, 2 / 23, 13 / 23))
    )


def transition(
    state: GateState, failed: bool, now: float, *, witness: str | None = None, language_only: bool = False
) -> GateState:
    gate = gate_rate()
    if state.threshold != gate:
        state = replace(
            state,
            threshold=gate,
            n=0,
            failures=0,
            evidence=GateState().evidence,
            witnesses=(),
            recent_failures=(),
            trial_users=(),
            healthy_users=(),
            healthy_window=-1,
            overflow_failures=(),
            trial_started_at=now if state.stage in (5, 25) else 0.0,
            generation=state.generation + 1,
        )
    if state.stage == 0:
        return state
    if state.stage == 100 and witness is not None:
        # An older async writer can win CAS after a newer window was opened.
        # Charge it to the current budget; never rewind and replenish a window.
        window = max(state.healthy_window, int(now // 300))
        users = dict(state.healthy_users) if window == state.healthy_window else {}
        count = users.get(witness, 0)
        # A bounded, success-reset outage witness run remains available even
        # after ordinary admission fills. It never feeds failure-only samples
        # into CUSUM, never evicts/refills user budgets, and cannot fill up without
        # benching: eight distinct new users failing with no intervening success.
        overflow = state.overflow_failures if window == state.healthy_window else ()
        if not failed:
            overflow = ()
        if overflow != state.overflow_failures:
            state = replace(state, overflow_failures=overflow)
        if not count and len(users) >= HEALTHY_USERS and failed:
            if witness not in overflow:
                overflow = (*overflow, witness)
            state = replace(state, overflow_failures=overflow)
            if len(overflow) == FAILURE_RESERVE:
                strikes = min(state.strikes + 1, 10)
                return GateState(
                    threshold=gate,
                    stage=0,
                    n=min(1_000_000, state.n + FAILURE_RESERVE),
                    failures=min(1_000_000, state.failures + FAILURE_RESERVE),
                    recent_failures=overflow,
                    until=now + min(14400, 300 * 2 ** (strikes - 1)),
                    strikes=strikes,
                    generation=state.generation + 1,
                )
        if count >= 3 or (not count and len(users) >= HEALTHY_USERS):
            return state
        users[witness] = count + 1
        state = replace(state, healthy_window=window, healthy_users=tuple(users.items()))
    required = {5: 30, 25: 60}.get(state.stage)
    if required and witness is not None:
        users = list(state.trial_users)
        index = next((i for i, user in enumerate(users) if user[0] == witness), len(users))
        if index == len(users):
            if len(users) >= 240:
                return state
            users.append((witness, 1, int(failed)))
        else:
            uid, count, failures = users[index]
            if count >= 3:
                return _promote_trial(state, now)
            users[index] = (uid, count + 1, failures + int(failed))
        state = replace(state, trial_users=tuple(users))
    if witness is not None and witness not in state.witnesses and len(state.witnesses) < 4:
        state = replace(state, witnesses=(*state.witnesses, witness))
    state = replace(state, recent_failures=(*state.recent_failures, (witness or '0' * 16) if failed else '')[-32:])
    # Fleet writers always supply a UID fingerprint. A single repeated caller
    # must not turn its failures into a fleet outage, even after healthy history.
    # Anonymous outcomes are used only by the mathematical simulation.
    counts = [state.recent_failures.count(uid) for uid in set(state.recent_failures) if uid]
    broad_failure = witness is None or (len(counts) >= 4 and max(counts) * 2 <= sum(counts))
    if required and state.trial_users:
        # Equal-weight user votes also protect late failures after a caller's
        # sequential-evidence budget is spent. One caller cannot be a majority.
        broad_failure = sum(failures * 2 > count for _, count, failures in state.trial_users) >= 4
    # Page CUSUM: each likelihood score resets at zero after negative evidence.
    # This is a change detector with empirically calibrated run lengths, NOT an
    # anytime-valid e-process or a posterior probability. Healthy-stage scores
    # do not reset at reporting-counter boundaries; held trial windows reset below.
    evidence = tuple(
        min(1000.0, max(0.0, old + increments[0 if failed else 1]))
        for old, increments in zip(state.evidence, _increments(gate))
    )
    n, failures = state.n + 1, state.failures + int(failed)
    user_rate = (
        sum(failures * 2 > count for _, count, failures in state.trial_users) / len(state.trial_users)
        if state.trial_users
        else failures / n
    )
    sparse_failure = language_only and len(counts) >= 2 and sum(counts) >= 16
    # The fast catastrophic score also needs eight recent failures; a rare
    # short burst of five failures must not bench a mostly healthy target.
    detected = evidence[0] >= 12 or evidence[1] >= 11 or (sum(counts) >= 8 and evidence[2] >= 10)
    decisive = (broad_failure and detected) or (sparse_failure and max(evidence) >= 14)
    if required:
        decisive = decisive and user_rate > gate
    rejected_trial = required and n >= required and user_rate > gate and broad_failure
    if n >= 8 and (decisive or rejected_trial):
        strikes = min(state.strikes + 1, 10)
        return GateState(
            threshold=gate,
            stage=0,
            n=n,
            failures=failures,
            evidence=evidence,
            recent_failures=state.recent_failures,
            trial_users=state.trial_users,
            until=now + min(14400, 300 * 2 ** (strikes - 1)),
            strikes=strikes,
            generation=state.generation + 1,
        )
    if required:
        promoted = _promote_trial(replace(state, n=n, failures=failures, evidence=evidence), now)
        if promoted.stage != state.stage:
            return promoted
    if required and n >= 4 * required:
        # A new bounded user-vote window, with the same share and strike history.
        return replace(
            state,
            n=0,
            failures=0,
            trial_users=(),
            evidence=GateState().evidence,
            recent_failures=(),
            witnesses=(),
        )
    if n >= 1_000_000:
        return replace(state, n=0, failures=0, evidence=evidence)
    return replace(
        state,
        n=n,
        failures=failures,
        evidence=evidence,
        strikes=0 if n >= 1024 and failures / n <= gate else state.strikes,
    )


def _promote_trial(state: GateState, now: float) -> GateState:
    """Promote a trial stage purely from already-admitted evidence and dwell."""
    required = {5: 30, 25: 60}.get(state.stage)
    if required is None or not state.trial_users:
        return state
    breadth = {5: 10, 25: 20}[state.stage]
    dwell = {5: 300.0, 25: 600.0}[state.stage]
    user_rate = sum(failures * 2 > count for _, count, failures in state.trial_users) / len(state.trial_users)
    if (
        state.n >= required
        and len(state.trial_users) >= breadth
        and now - state.trial_started_at >= dwell
        and user_rate <= gate_rate()
    ):
        return GateState(
            threshold=state.threshold,
            stage=25 if state.stage == 5 else 100,
            strikes=state.strikes,
            generation=state.generation + 1,
            trial_started_at=now,
        )
    return state


def begin_trial(state: GateState, now: float) -> GateState:
    if state.stage == 0 and now >= state.until:
        return GateState(
            threshold=state.threshold,
            stage=5,
            strikes=state.strikes,
            generation=state.generation + 1,
            trial_started_at=now,
        )
    return state
