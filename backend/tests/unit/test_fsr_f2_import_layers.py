"""Read-cache persistence and rollout gates must stay below business logic."""

import ast
import logging
from pathlib import Path

from database import fsr_cache_telemetry
from utils.observability import fallback

BACKEND = Path(__file__).resolve().parents[2]


def test_cache_and_gate_do_not_import_business_logic():
    for path in (
        BACKEND / 'database/fsr_read_cache.py',
        BACKEND / 'database/fsr_cache_telemetry.py',
        BACKEND / 'config/firestore_read_levers.py',
    ):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            )
            assert not any(name.split('.')[0] in {'utils', 'routers', 'main'} for name in names), path


def test_cache_fallback_retains_shared_counter_and_label_contract(caplog):
    assert fsr_cache_telemetry.OMI_FALLBACK_TOTAL is fallback.OMI_FALLBACK_TOTAL
    labels = dict(
        component='other', from_mode='subscription_cache', to_mode='firestore', reason='other', outcome='degraded'
    )
    counter = fallback.OMI_FALLBACK_TOTAL.labels(**labels)
    before = next(
        sample.value for metric in counter.collect() for sample in metric.samples if sample.name.endswith('_total')
    )
    fsr_cache_telemetry.record_fallback(
        component='firestore_read_cache',
        from_mode='subscription_cache',
        to_mode='firestore',
        reason='redis_read_error',
        outcome='degraded',
        log=logging.getLogger(__name__),
    )
    after = next(
        sample.value for metric in counter.collect() for sample in metric.samples if sample.name.endswith('_total')
    )
    assert after == before + 1
    assert fallback.bucket_component('firestore_read_cache') == labels['component']
    assert fallback.bucket_reason('redis_read_error') == labels['reason']
    assert (
        'omi_fallback_event component=other from=subscription_cache to=firestore reason=other outcome=degraded'
        in caplog.text
    )
