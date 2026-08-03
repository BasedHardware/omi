"""Deterministic gold-freeze and warn-only drift helpers for parity packs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class Drift:
    case_id: str
    expected_digest: str
    actual_digest: str


def result_digest(result: Mapping[str, Any]) -> str:
    """Return a stable digest without retaining result payloads in reports."""
    return sha256(_canonical(dict(result)).encode()).hexdigest()


def double_run_gold(
    manifest_path: Path,
    run_case: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    *,
    write_gold: bool = False,
) -> tuple[Drift, ...]:
    """Run every manifest case twice, reject nondeterminism, optionally freeze gold.

    ``write_gold`` is deliberately explicit: ordinary replay only reports drift;
    it never changes a local pack's expected outcomes as a side effect.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    drifts: list[Drift] = []
    for case in manifest["cases"]:
        first = dict(run_case(case))
        second = dict(run_case(case))
        first_digest, second_digest = result_digest(first), result_digest(second)
        if first_digest != second_digest:
            raise AssertionError(f"non-deterministic replay for {case['case_id']}")
        expected = dict(case.get("expected_outcomes", {}))
        expected_digest = result_digest(expected)
        if expected_digest != first_digest:
            drifts.append(Drift(case["case_id"], expected_digest, first_digest))
            if write_gold:
                case["expected_outcomes"] = first
    if write_gold:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tuple(drifts)


def drift_report(drifts: tuple[Drift, ...]) -> dict[str, Any]:
    """A payload-free, warn-only report suitable for local operator output."""
    return {
        "status": "warn" if drifts else "ok",
        "drift_count": len(drifts),
        "drifts": [drift.__dict__ for drift in drifts],
        "enforcement": "warn-only",
    }
