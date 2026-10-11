#!/usr/bin/env python3
"""Hermetic cost-v6 calibration; synthetic counts only, no service clients.

Run from backend: .venv/bin/python scripts/stt/calibrate_live_gate.py
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.stt.live_gate import GateState, transition
from utils.stt.live_signal import provider_observation


def baseline(seed: int, rate: float, floor: float, sessions: int = 20000) -> tuple[int, int]:
    rng, state = random.Random(seed), GateState()
    benches = classified = 0
    for i in range(sessions):
        # 17.9k sessions/day; repeated users, not one UID per session.
        now, witness = i * 86400 / 17900, f'{rng.randrange(1000):016x}'
        draw = rng.random()
        outcome = 'failover' if draw < rate else 'no_text' if draw < rate + floor else 'text'
        failed = provider_observation(outcome, 'modulate_serve_error')
        if failed is None:
            continue
        previous_n = state.n
        state = transition(state, failed, now, witness=witness)
        classified += int(state.n > previous_n)
        if state.stage == 0:
            benches += 1
            state = GateState()
    return benches, classified


def detection(seed: int, rate: float, *, churn: bool = False) -> tuple[int, int, int]:
    rng, state, failures, raw = random.Random(seed), GateState(), 0, 0
    for i in range(500):
        state = transition(state, False, i * 5, witness=f'{i:016x}')
    for n in range(1, 5001):
        now = 2500 + n * 300 / 62
        if churn:
            # Forty-six extra reconnects from one user cannot manufacture an
            # outage or buy away genuine evidence with passing votes.
            for _ in range(46 if n == 1 else 0):
                state = transition(state, False, now, witness='f' * 16)
                raw += 1
        draw = rng.random()
        failed = provider_observation(
            'failover' if draw < rate else 'no_text' if draw < rate + 0.10 else 'text', 'modulate_serve_error'
        )
        raw += 1
        if failed is not None:
            failures += int(failed)
            state = transition(state, failed, now, witness=f'{rng.randrange(1000) + 500:016x}')
        if state.stage == 0:
            return n, failures, raw
    return 5001, failures, raw


def main() -> None:
    os.environ['STT_ROUTING_DISRUPTION_GATE'] = '0.08'
    report: dict = {'state_prefix': 'cost-v6', 'baselines': [], 'detection': []}
    for rate, floor in ((0, 0.05), (0, 0.07), (0, 0.10), (0.003, 0.10), (0.01, 0.10), (0.03, 0.10)):
        runs = [baseline(seed, rate, floor) for seed in range(20)]
        report['baselines'].append(
            dict(
                provider_rate=rate,
                no_text_floor=floor,
                sessions=400000,
                false_benches=sum(n for n, _ in runs),
                votes=sum(n for _, n in runs),
            )
        )
    for rate in (0.4, 0.6, 1.0):
        for churn in (False, True):
            runs = [detection(seed, rate, churn=churn) for seed in range(200)]
            sessions, failures, raw = zip(*runs)
            report['detection'].append(
                dict(
                    provider_rate=rate,
                    one_user_churn=churn,
                    runs=200,
                    sessions_median=statistics.median(sessions),
                    sessions_p95=sorted(sessions)[189],
                    failures_median=statistics.median(failures),
                    failures_p95=sorted(failures)[189],
                    sessions_max=max(sessions),
                    raw_sessions_p95=sorted(raw)[189],
                )
            )
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
