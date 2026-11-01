"""Single aggregate-only entry point. Default execution is entirely offline."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import random
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any, IO, cast

from evals.dream_verifier.audit import reconcile
from evals.dream_verifier.contracts import ROOT, canonical, digest, load_items, model_input
from evals.dream_verifier.detection import evaluate_detection
from evals.dream_verifier.deterministic import check
from evals.dream_verifier.gateway import Routes, model_arm, require_replay_pod
from evals.dream_verifier.generate import SEED, STRATA
from evals.dream_verifier.metrics import Aggregate, promotion
from evals.dream_verifier.policy import preamble

ARMS = ('flash_two', 'flash_one', 'flash_lite', 'jev', 'deterministic', 'deterministic_cheap')
KINDS = {
    'spelling',
    'title',
    'overview',
    'retire_memory',
    'supersede_memory',
    'close_task',
    'merge_tasks',
    'retire_task',
    'vocabulary',
    'merge_people',
    'merge_conversations',
    'set_language',
    'memory',
    'merge_memories',
    'entity_summary',
    'dismiss_person',
    'same_person',
}


async def evaluate(
    items: Iterable[dict[str, Any]],
    *,
    arms: tuple[str, ...] = ('deterministic',),
    routes: Routes = Routes(),
    cheap_arm: str = 'jev',
    audited: bool = False,
) -> dict[str, Any]:
    """Also used by the prepared owner adapter; no per-item serialization/output."""
    if not arms or set(arms) - set(ARMS) or len(set(arms)) != len(arms) or cheap_arm not in {'jev', 'flash_lite'}:
        raise ValueError('invalid_arm_selection')
    if any(arm != 'deterministic' for arm in arms):
        require_replay_pod()
    if not 0 <= routes.jev_no < routes.jev_yes <= 1:
        raise ValueError('invalid_jev_thresholds')
    metrics: dict[tuple[str, str, str], Aggregate] = {}
    totals = {arm: Aggregate() for arm in arms}
    seen: set[str] = set()
    policy_hashes: set[str] = set()
    families: dict[tuple[str, str], set[str]] = {}
    for index, item in enumerate(items):
        model_input(item)
        policy = preamble(item)
        if policy:
            policy_hashes.add(digest(policy))
        if item['id'] in seen or item['gold'] not in {'accept', 'reject'}:
            raise ValueError('duplicate_id_or_invalid_gold')
        seen.add(item['id'])
        bounded_kind = item['staged']['kind'] if item['staged']['kind'] in KINDS else 'other'
        if item.get('template_family'):
            families.setdefault((bounded_kind, item['gold']), set()).add(item['template_family'])
        # Rotate arm order across items to reduce shared warm-cache order bias.
        order = list(arms[index % len(arms) :] + arms[: index % len(arms)])
        for arm in order:
            if arm in {'deterministic', 'deterministic_cheap'}:
                started = time.monotonic()
                outcome = check(item)
                if arm == 'deterministic_cheap' and outcome.decision == 'review':
                    outcome = await model_arm(item, cheap_arm, routes)
                    if outcome.decision == 'unverified':
                        outcome.decision = 'review'
                outcome.latency_ms = (time.monotonic() - started) * 1000
            else:
                outcome = await model_arm(item, arm, routes)
            kind = item['staged']['kind'] if item['staged']['kind'] in KINDS else 'other'
            stratum = str(item.get('stratum')) if item.get('stratum') in STRATA else 'other'
            for key in (('kind', kind, arm), ('stratum', stratum, arm)):
                metrics.setdefault(key, Aggregate()).add(item['gold'], outcome)
            totals[arm].add(item['gold'], outcome)
        # Real owner evidence is released by the streaming caller; only counts,
        # timings, rate-card IDs and opaque seen-ID hashes remain in this loop.
    groups: dict[str, dict[str, Any]] = {'kind': {}, 'stratum': {}}
    for (group, name, arm), aggregate in metrics.items():
        groups[group].setdefault(name, {})[arm] = aggregate.report()
    for by_kind in groups['kind'].values():
        for arm, values in by_kind.items():
            values['promotion'] = (
                'reference' if arm == 'flash_two' else promotion(values, by_kind.get('flash_two'), audited=audited)
            )
    return {
        'schema_version': 1,
        'items': len(seen),
        'label_audit_complete': audited,
        'batch_policy': 'singleton_same_evidence_two_independent_baseline_calls',
        'cost_basis': 'gateway_rate_cards_all_attempts_unknown_is_null',
        'cheap_arm': cheap_arm,
        'jev_thresholds': {'yes': routes.jev_yes, 'no': routes.jev_no},
        'totals': {arm: aggregate.report() for arm, aggregate in totals.items()},
        'per_kind': groups['kind'],
        'per_stratum': groups['stratum'],
        'automatic_rollout': False,
        'policy_sha256': sorted(policy_hashes),
        'independent_draws_established': False,
        'design_family_counts': {
            kind: {label: len(families.get((kind, label), set())) for label in ('accept', 'reject')}
            for kind in sorted({key[0] for key in families})
        },
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'synthetic.v2.jsonl')
    parser.add_argument('--arms', default='deterministic')
    parser.add_argument('--cheap-arm', choices=('jev', 'flash_lite'), default='jev')
    parser.add_argument('--flash-lane', default=Routes.flash)
    parser.add_argument('--lite-lane', default=Routes.lite)
    parser.add_argument('--jev-yes', type=float, default=0.99)
    parser.add_argument('--jev-no', type=float, default=0.01)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--detection', action='store_true')
    parser.add_argument('--jev-triage', action='store_true')
    parser.add_argument('--audit', nargs=2, type=Path, metavar=('LUNA', 'GROK'))
    parser.add_argument('--adjudication', type=Path)
    parser.add_argument('--audit-receipt', type=Path)
    return parser.parse_args()


class Discard:
    def write(self, value: str) -> int:
        return len(value)

    def flush(self) -> None:
        pass


async def main(args: argparse.Namespace) -> dict[str, Any]:
    routes = Routes(args.flash_lane, args.lite_lane, args.jev_yes, args.jev_no)
    if args.detection:
        if args.jev_triage:
            require_replay_pod()
        return await evaluate_detection(jev=args.jev_triage, routes=routes)
    items = load_items(args.dataset)
    audit = reconcile(items, args.audit[0], args.audit[1], args.adjudication) if args.audit else None
    dataset_hash = digest(items)
    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError('limit_must_be_positive')
        random.Random(SEED).shuffle(items)
        items = items[: args.limit]
    if args.audit:
        # Audit-only invocation makes no model calls.
        assert audit is not None
        return audit
    audited = False
    if args.audit_receipt:
        receipt = json.loads(args.audit_receipt.read_text())
        if receipt.get('dataset_sha256') != dataset_hash or receipt.get('audit_complete') is not True:
            raise ValueError('audit_receipt_mismatch_or_incomplete')
        audited = True
    result = await evaluate(
        items, arms=tuple(args.arms.split(',')), routes=routes, cheap_arm=args.cheap_arm, audited=audited
    )
    result['dataset_sha256'] = dataset_hash
    result['audit_status'] = 'audited' if audited else 'pending_run_audit_and_expand_dataset_before_promotion'
    return result


if __name__ == '__main__':
    args = arguments()
    # Libraries must not print provider bodies, evidence, exception text or UIDs.
    # Logs are discarded, not buffered or written to disk. Exactly one JSON object
    # is emitted after restoring stdout, including a bounded failure code.
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(cast(IO[str], Discard())), contextlib.redirect_stderr(cast(IO[str], Discard())):
            result = asyncio.run(main(args))
    except Exception:
        print(
            canonical(
                {
                    'schema_version': 1,
                    'error': 'benchmark_failed_check_configuration_or_dataset',
                    'automatic_rollout': False,
                }
            )
        )
        sys.exit(1)
    print(canonical(result))
