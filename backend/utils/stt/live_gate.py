"""Session-counted binary gate. Pure transitions are also used by Redis CAS."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from typing import Any


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
    witnesses: tuple[str, ...] = ()
    recent_failures: tuple[str, ...] = ()

    @classmethod
    def decode(cls, raw: dict[str, Any]) -> GateState:
        raw = dict(raw)
        if not all(type(raw.get(field, 0)) is int for field in ('n', 'failures', 'generation', 'strikes', 'stage')):
            raise ValueError('invalid cost gate counts')
        raw['evidence'] = tuple(raw.get('evidence', cls().evidence))
        for field in ('witnesses', 'recent_failures'):
            values: list[Any] = list(raw.get(field, ()))
            if any(
                not isinstance(value, str) or (len(value) != 16 and not (field == 'recent_failures' and value == ''))
                for value in values
            ):
                raise ValueError('invalid cost gate witnesses')
            raw[field] = tuple(values)
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
            or state.generation < 0
            or not 0 <= state.strikes <= 10
            or len(state.witnesses) > 4
            or len(set(state.witnesses)) != len(state.witnesses)
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
            generation=state.generation + 1,
        )
    if state.stage == 0:
        return state
    if witness is not None and witness not in state.witnesses and len(state.witnesses) < 4:
        state = replace(state, witnesses=(*state.witnesses, witness))
    state = replace(state, recent_failures=(*state.recent_failures, (witness or '0' * 16) if failed else '')[-32:])
    # Fleet writers always supply a UID fingerprint. A single repeated caller
    # must not turn its failures into a fleet outage, even after healthy history.
    # Anonymous outcomes are used only by the mathematical simulation.
    counts = [state.recent_failures.count(uid) for uid in set(state.recent_failures) if uid]
    broad_failure = witness is None or (len(counts) >= 4 and max(counts) * 2 <= sum(counts))
    # Page CUSUM: each likelihood score resets at zero after negative evidence.
    # This is a change detector with empirically calibrated run lengths, NOT an
    # anytime-valid e-process or a posterior probability. Scores do not reset
    # at reporting-counter boundaries.
    evidence = tuple(
        min(1000.0, max(0.0, old + increments[0 if failed else 1]))
        for old, increments in zip(state.evidence, _increments(gate))
    )
    n, failures = state.n + 1, state.failures + int(failed)
    required = {5: 30, 25: 60}.get(state.stage)
    sparse_failure = language_only and len(counts) >= 2 and sum(counts) >= 16
    # The fast catastrophic score also needs eight recent failures; a rare
    # short burst of five failures must not bench a mostly healthy target.
    detected = evidence[0] >= 12 or evidence[1] >= 11 or (sum(counts) >= 8 and evidence[2] >= 10)
    decisive = (broad_failure and detected) or (sparse_failure and max(evidence) >= 14)
    rejected_trial = required and n >= required and failures / n > gate and broad_failure
    if n >= 8 and (decisive or rejected_trial):
        strikes = min(state.strikes + 1, 10)
        return GateState(
            threshold=gate,
            stage=0,
            n=n,
            failures=failures,
            evidence=evidence,
            recent_failures=state.recent_failures,
            until=now + min(14400, 300 * 2 ** (strikes - 1)),
            strikes=strikes,
            generation=state.generation + 1,
        )
    if required and n >= required and failures / n <= gate:
        return GateState(
            threshold=gate,
            stage=25 if state.stage == 5 else 100,
            strikes=state.strikes,
            generation=state.generation + 1,
        )
    if required and n >= 4 * required:
        # Narrow failures cannot spend a fleet strike. Keep the trial share,
        # but bound its rate window so later healthy sessions can promote it.
        # Sequential scores and recent failure breadth remain intact.
        return replace(state, n=0, failures=0, evidence=evidence)
    if n >= 1_000_000:
        return replace(state, n=0, failures=0, evidence=evidence)
    return replace(
        state,
        n=n,
        failures=failures,
        evidence=evidence,
        strikes=0 if n >= 1024 and failures / n <= gate else state.strikes,
    )


def begin_trial(state: GateState, now: float) -> GateState:
    if state.stage == 0 and now >= state.until:
        return GateState(threshold=state.threshold, stage=5, strikes=state.strikes, generation=state.generation + 1)
    return state
