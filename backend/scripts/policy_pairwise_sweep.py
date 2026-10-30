#!/usr/bin/env python3
"""Run the complete seeded batch/listen pairwise policy sweep in pipeline_sim."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from time import monotonic

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.policy.generator import generate_policy_cases, policy_pairwise_array  # noqa: E402
from testing.hermetic_network import block_outbound_network  # noqa: E402
from testing.pipeline_sim.policy_invariants import assert_policy_invariants, simulate_policy_case  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=1, help='seed for the covering array and simulated inputs')
    args = parser.parse_args(argv)

    array = policy_pairwise_array(args.seed)
    cases = generate_policy_cases(args.seed)
    started = monotonic()
    paid_calls = 0
    logging.disable(logging.CRITICAL)
    with block_outbound_network():
        for case in cases:
            result = simulate_policy_case(case, seed=args.seed + case.index)
            assert_policy_invariants(result)
            paid_calls += result.modulate.calls

    elapsed = monotonic() - started
    print(
        'policy pairwise sweep: '
        f'seed={args.seed} factors={array.factor_count} '
        f'feasible_pairs={array.feasible_pair_count} covered_pairs={array.covered_pair_count} '
        f'covering_rows={len(cases)} candidates={array.candidate_count} '
        f'simulated={len(cases)} paid_calls={paid_calls} '
        f'invariant_failures=0 elapsed_seconds={elapsed:.3f}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
