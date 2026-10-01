"""Session-counted binary gate. Pure transitions are also used by Redis CAS."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class GateState:
    threshold: float = 0.08
    stage: int = 100
    n: int = 0
    failures: int = 0
    evidence: tuple[float, ...] = (-745.0, -745.0, -745.0)
    until: float = 0
    strikes: int = 0
    generation: int = 0

    @classmethod
    def decode(cls, raw: dict) -> GateState:
        raw = dict(raw)
        raw['evidence'] = tuple(raw.get('evidence', cls().evidence))
        state = cls(**raw)
        if (
            not math.isfinite(state.threshold)
            or not 0 < state.threshold < 1
            or state.stage not in (0, 5, 25, 100)
            or not isinstance(state.n, int)
            or not 0 <= state.failures <= state.n <= 1024
            or len(state.evidence) != 3
            or not all(math.isfinite(value) for value in state.evidence)
            or not math.isfinite(state.until)
            or state.until < 0
            or not isinstance(state.generation, int)
            or state.generation < 0
            or not isinstance(state.strikes, int)
            or not 0 <= state.strikes <= 10
        ):
            raise ValueError('invalid cost gate state')
        return state

    def encode(self) -> dict:
        return asdict(self)


def gate_rate() -> float:
    gate = float(os.getenv('STT_ROUTING_DISRUPTION_GATE', '0.08'))
    if not math.isfinite(gate) or not 0 < gate < 1:
        raise ValueError('disruption gate must be between 0 and 1')
    return gate


def transition(state: GateState, failed: bool, now: float) -> GateState:
    gate = gate_rate()
    if state.threshold != gate:
        state = replace(
            state, threshold=gate, n=0, failures=0, evidence=GateState().evidence, generation=state.generation + 1
        )
    if state.stage == 0:
        return state
    # Invest 1/1024 of the evidence budget in a new change point each session.
    # Existing investments continue compounding; the uninvested reserve makes
    # the sum an anytime-valid martingale within each 1024-session block.
    evidence = tuple(
        max(old, -math.log(1024))
        + math.log1p(math.exp(-abs(old + math.log(1024))))
        + math.log(q / gate if failed else (1 - q) / (1 - gate))
        for old, q in zip(state.evidence, (gate + (1 - gate) * fraction for fraction in (2 / 23, 11 / 46, 18 / 23)))
    )
    n, failures = state.n + 1, state.failures + int(failed)
    peak = max(evidence)
    log_e = peak + math.log(sum(math.exp(value - peak) for value in evidence) / len(evidence))
    if n >= 8 and log_e >= math.log(1000):
        strikes = min(state.strikes + 1, 10)
        return GateState(
            threshold=gate,
            stage=0,
            n=n,
            failures=failures,
            until=now + min(14400, 300 * 2 ** (strikes - 1)),
            strikes=strikes,
            generation=state.generation + 1,
        )
    required = {5: 30, 25: 60}.get(state.stage)
    if required and n >= required:
        if failures / n > gate:
            strikes = min(state.strikes + 1, 10)
            return GateState(
                threshold=gate,
                stage=0,
                n=n,
                failures=failures,
                until=now + min(14400, 300 * 2 ** (strikes - 1)),
                strikes=strikes,
                generation=state.generation + 1,
            )
        return GateState(
            threshold=gate,
            stage=25 if state.stage == 5 else 100,
            strikes=state.strikes,
            generation=state.generation + 1,
        )
    if n >= 1024:
        return GateState(threshold=gate, stage=state.stage, generation=state.generation + 1)
    return replace(state, n=n, failures=failures, evidence=evidence)


def begin_trial(state: GateState, now: float) -> GateState:
    if state.stage == 0 and now >= state.until:
        return GateState(threshold=state.threshold, stage=5, strikes=state.strikes, generation=state.generation + 1)
    return state
