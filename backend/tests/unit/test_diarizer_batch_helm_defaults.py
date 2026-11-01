"""Regression pins for the diarizer-batch release autoscaling contract.

The batch diarizer holds one n1-standard-8 + T4 node per replica; its only
scale signal is the per-pod omi_diarization_v2_queue_depth metric exposed by
the prometheus-adapter. The gauge reports 0..3 (AdmissionQueue capacity,
backend/diarizer/admission.py). These pins keep the queue-depth target
(raised 1 -> 2 on 2026-11-01, marginfleet) from silently reverting to
one-node-per-item provisioning, keep it strictly below the metric ceiling so
a saturated pod always reads above target and scales out, and keep the
David-only floor at 1.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = ROOT / "backend" / "charts" / "diarizer"
PROD_VALUES = CHART_DIR / "prod_omi_diarizer_values.yaml"
BATCH_VALUES = CHART_DIR / "prod_omi_diarizer_batch_values.yaml"


def _admission_capacity() -> int:
    """Import backend.diarizer.admission without importing the app package."""
    spec = importlib.util.spec_from_file_location(
        "marginfleet_admission_probe", ROOT / "backend" / "diarizer" / "admission.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queue = module.AdmissionQueue()
    try:
        return queue.pending.maxsize
    finally:
        queue.executor.shutdown(wait=False)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _render() -> dict:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("helm is not installed")
    output = subprocess.check_output(
        [
            helm,
            "template",
            "prod-omi-diarizer-batch",
            str(CHART_DIR),
            "-f",
            str(PROD_VALUES),
            "-f",
            str(BATCH_VALUES),
            "--set-string",
            "image.tag=diarizer-batch-contract-test",
        ],
        text=True,
    )
    objects = [obj for obj in yaml.load_all(output, Loader=yaml.CSafeLoader) if obj]
    by_kind: dict[str, list[dict]] = {}
    for obj in objects:
        by_kind.setdefault(obj["kind"], []).append(obj)
    hpas = by_kind.get("HorizontalPodAutoscaler", [])
    assert len(hpas) == 1, f"expected exactly one HPA, rendered {len(hpas)}"
    return hpas[0]


def test_batch_values_pin_queue_depth_target_and_floor():
    values = _load(BATCH_VALUES)["autoscaling"]
    assert values["enabled"] is True
    assert values["minReplicas"] == 1, "floor is David-only at 1; see file header"
    assert values["maxReplicas"] == 18
    target = values["queueDepthAverageValue"]
    assert target == 2, (
        "target 1 provisions one T4 node per queued item (2026-11-01 measurement: "
        "queue p50=0, max=4, ~3 idle T4 nodes); raise only with a fresh queue read"
    )
    assert values["requestLatencyP99"] is None, "batch release must not scale on live p99"


def test_batch_queue_depth_target_stays_below_metric_ceiling():
    capacity = _admission_capacity()
    target = _load(BATCH_VALUES)["autoscaling"]["queueDepthAverageValue"]
    assert target < capacity, (
        f"the queue-depth gauge reports 0..{capacity} (AdmissionQueue capacity); at "
        f"target >= {capacity} a saturated pod reads at or below target and the HPA "
        "never scales out while CapacityExceeded rejects uploads (Luna r1 P1)"
    )


def test_batch_hpa_renders_single_queue_depth_metric():
    spec = _render()["spec"]
    assert spec["minReplicas"] == 1
    assert spec["maxReplicas"] == 18
    metrics = spec["metrics"]
    assert len(metrics) == 1, f"expected only the queue-depth metric, got {metrics}"
    pods = metrics[0]["pods"]
    assert pods["metric"]["name"] == "omi_diarization_v2_queue_depth"
    assert pods["target"] == {"type": "AverageValue", "averageValue": "2"}
