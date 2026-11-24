"""Projection-finish counters must survive the backend-integration GMP keep rule.

``backend-integration`` is the only service running the projection finish sweep
(``BATCH_PIPELINE_SERVING_ENABLED``), so ``omi_batch_projection_finish_reads_total``
and ``omi_batch_projection_finish_completed_total`` are born there. The sync
collector's ``__name__`` keep rule named every other ``batch_projection_*``
counter but these two, so the finish-backoff alert
(``charts/monitoring/batch-projection/alerts.yaml``) and the re-enable bar in
``docs/runbooks/projection-finish-backfill.md`` read empty in GMP while the
sweep kept working (FC-metric-dropped-by-scrape-allowlist).

The names are pinned from the producer registration, not copied by hand, so a
rename in the emitter fails here instead of silently emptying the readout.
Both counters are label-free, so the addition costs two series per instance.
"""

import re
from pathlib import Path

import yaml
from prometheus_client import REGISTRY

import utils.batch_pipeline.metrics  # noqa: F401  (registers the counters)

BACKEND = Path(__file__).resolve().parents[2]
SYNC_PROFILE = BACKEND / 'deploy' / 'cloud_run_gmp_sync.yaml'
SHARED_PROFILE = BACKEND / 'deploy' / 'cloud_run_gmp_sidecar.yaml'

FINISH_SAMPLES = (
    'omi_batch_projection_finish_reads_total',
    'omi_batch_projection_finish_completed_total',
)


def _relabels(profile):
    config = yaml.safe_load(profile.read_text(encoding='utf-8'))
    return config['spec']['endpoints'][0]['metricRelabeling']


def _kept(name, relabels, component=''):
    labels = {'__name__': name, 'component': component}
    for rule in relabels:
        value = ';'.join(labels.get(key, '') for key in rule['sourceLabels'])
        matched = re.fullmatch(rule['regex'], value)
        if rule['action'] == 'keep' and not matched:
            return False
        if rule['action'] == 'drop' and matched:
            return False
    return True


def test_producer_registers_the_finish_counters():
    # prometheus_client strips the _total suffix from a Counter family name.
    emitted = {metric.name for metric in REGISTRY.collect()}
    assert {'omi_batch_projection_finish_reads', 'omi_batch_projection_finish_completed'} <= emitted


def test_finish_counters_survive_the_sync_keep_rule():
    relabels = _relabels(SYNC_PROFILE)
    missing = [name for name in FINISH_SAMPLES if not _kept(name, relabels)]
    assert not missing, f'backend-integration GMP keep rule drops {missing}'


def test_finish_counters_survive_the_shared_profile():
    # The shared profile keeps omi_.*; pin it so a future narrowing cannot drop them there.
    relabels = _relabels(SHARED_PROFILE)
    missing = [name for name in FINISH_SAMPLES if not _kept(name, relabels)]
    assert not missing, missing


def test_neighbouring_projection_families_still_survive():
    relabels = _relabels(SYNC_PROFILE)
    for name in (
        'omi_batch_projection_drains_skipped_total',
        'omi_batch_projection_claim_busy_backoffs_total',
        'omi_batch_projection_drain_oldest_age_seconds',
    ):
        assert _kept(name, relabels), name


def test_unrelated_finish_families_stay_dropped():
    # The addition is explicit names, not a batch_projection_finish_.* catch-all.
    relabels = _relabels(SYNC_PROFILE)
    for name in (
        'omi_batch_projection_finish_retries_total',
        'omi_batch_projection_finished_total',
        'omi_batch_projection_finish_reads',
    ):
        assert not _kept(name, relabels), name
