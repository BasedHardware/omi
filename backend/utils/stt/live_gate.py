"""Session-counted binary gate. Pure transitions are also used by Redis CAS."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, replace
from typing import Any


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
            if any(not isinstance(value, str) or len(value) != 16 for value in values):
                raise ValueError('invalid cost gate witnesses')
            raw[field] = tuple(values)
        state = cls(**raw)
        if (
            not math.isfinite(state.threshold)
            or not 0 < state.threshold < 1
            or state.stage not in (0, 5, 25, 100)
            or not 0 <= state.failures <= state.n <= 1024
            or len(state.evidence) != 3
            or not all(math.isfinite(value) for value in state.evidence)
            or not math.isfinite(state.until)
            or state.until < 0
            or state.generation < 0
            or not 0 <= state.strikes <= 10
            or len(state.witnesses) > 4
            or len(set(state.witnesses)) != len(state.witnesses)
            or len(state.recent_failures) > 8
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


def transition(state: GateState, failed: bool, now: float, *, witness: str | None = None) -> GateState:
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
    if witness is not None and failed:
        state = replace(state, recent_failures=(*state.recent_failures, witness)[-8:])
    # Fleet writers always supply a UID fingerprint. A single repeated caller
    # must not turn its failures into a fleet outage, even after healthy history.
    # Anonymous outcomes are used only by the mathematical simulation.
    diverse = witness is None or len(state.witnesses) >= 4
    broad_failure = witness is None or len(set(state.recent_failures)) >= 4
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
    required = {5: 30, 25: 60}.get(state.stage)
    if broad_failure and n >= 8 and (log_e >= math.log(1000) or (required and n >= required and failures / n > gate)):
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
    if diverse and required and n >= required and failures / n <= gate:
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
