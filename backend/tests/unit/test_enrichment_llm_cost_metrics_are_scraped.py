"""Enrichment LLM cost/usage families must survive the backend-integration GMP keep rule.

SCA-2057 (2026-11-13) proved the blind spot: ``backend-integration`` runs the
enrichment consumer, but the sync collector's ``__name__`` keep rule dropped
``omi_conversation_llm_calls_total``, ``omi_shaped_agent_input_tokens_total``,
``omi_notes_agent_*`` and ``omi_episode_moment_cost_usd_total``. The SCA-1960
guardrail regression therefore had no attributable cost readout
(FC-metric-dropped-by-scrape-allowlist).

The families are derived from the producer registrations, not copied by hand, so
a rename in the emitter fails here instead of silently emptying the readout.
Cost families stay estimates: the gateway ledger is authoritative, and an empty
vector means "not scraped", never "zero spend".
"""

import re
from pathlib import Path

import pytest
import yaml
from prometheus_client import REGISTRY

# Importing the producers registers their collectors on the default registry.
import utils.episodes.metrics  # noqa: F401
import utils.llm.notes_agent  # noqa: F401
import utils.llm.notes_agent_serving  # noqa: F401
import utils.llm.shaped_agent  # noqa: F401
import utils.sync.repeat_work_metrics  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]
SYNC_PROFILE = BACKEND / 'deploy' / 'cloud_run_gmp_sync.yaml'
SHARED_PROFILE = BACKEND / 'deploy' / 'cloud_run_gmp_sidecar.yaml'

# The four families SCA-2057 found missing from the integration scrape.
REQUIRED_PREFIXES = (
    'omi_conversation_llm_calls',
    'omi_shaped_agent_input_tokens',
    'omi_notes_agent_',
    'omi_episode_moment_',
)
# Episode-moment latency is not part of the cost readout; keep the addition narrow.
EXCLUDED = {
    'omi_episode_moment_update_latency_seconds_bucket',
    'omi_episode_moment_update_latency_seconds_count',
    'omi_episode_moment_update_latency_seconds_sum',
    'omi_episode_moments_skipped_no_client_total',
}


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


def _emitted_samples():
    """Sample names the producers expose, including unobserved counters.

    ``prometheus_client`` strips ``_total`` from a Counter family name and emits
    no sample until the first increment, so expand by collector type instead of
    reading ``collect()`` samples.
    """
    names = set()
    for metric in REGISTRY.collect():
        if metric.type == 'counter':
            names.add(metric.name + '_total')
        elif metric.type == 'histogram':
            names.update({metric.name + suffix for suffix in ('_bucket', '_count', '_sum')})
        else:
            names.add(metric.name)
    return names


def _required_samples():
    return {name for name in _emitted_samples() if name.startswith(REQUIRED_PREFIXES) and name not in EXCLUDED}


def test_producers_register_the_required_families():
    required = _required_samples()
    # One representative per family, so a wholesale import failure is not read as "nothing to keep".
    for name in (
        'omi_conversation_llm_calls_total',
        'omi_shaped_agent_input_tokens_total',
        'omi_notes_agent_runs_total',
        'omi_notes_agent_estimated_cost_usd_bucket',
        'omi_notes_agent_transport_skips_total',
        'omi_episode_moment_cost_usd_total',
        'omi_episode_moment_tokens_total',
        'omi_episode_moment_updates_total',
    ):
        assert name in required, name


def test_every_required_sample_survives_the_sync_keep_rule():
    relabels = _relabels(SYNC_PROFILE)
    missing = sorted(name for name in _required_samples() if not _kept(name, relabels))
    assert not missing, f'backend-integration GMP keep rule drops {missing}'


def test_required_families_also_survive_the_shared_profile():
    # The shared profile keeps omi_.*; pin it so a future narrowing cannot drop them there.
    relabels = _relabels(SHARED_PROFILE)
    missing = sorted(name for name in _required_samples() if not _kept(name, relabels))
    assert not missing, missing


def test_existing_retained_families_still_survive():
    relabels = _relabels(SYNC_PROFILE)
    for name in (
        'omi_enrichment_early_abort_total',
        'omi_enrichment_supersede_streak_bucket',
        'omi_enrichment_obligation_total',
        'omi_batch_pipeline_events_total',
        'omi_parakeet_request_seconds_bucket',
        'omi_firestore_billed_reads_by_caller_total',
        'omi_accept_to_summary_seconds_bucket',
        'omi_summary_terminal_total',
        'omi_live_session_transcript_outcome_total',
        'omi_batch_projection_drains_skipped_total',
        'omi_batch_projection_finish_reads_total',
        'omi_batch_projection_finish_completed_total',
    ):
        assert _kept(name, relabels), name


def test_unrelated_families_stay_dropped():
    relabels = _relabels(SYNC_PROFILE)
    for name in (
        'omi_stt_cost_routing_settlements_total',
        'omi_subscription_events_total',
        'omi_product_event_total',
        'omi_vertex_non_dream_flash_after_cutover_attempts_total',
        # Near misses: the addition is explicit names, not a notes_agent_/episode_moment_ catch-all.
        'omi_notes_agent_other_total',
        'omi_notes_agent_runs',
        'omi_episode_moment_cost_usd',
        'omi_episode_moment_update_latency_seconds_bucket',
        'omi_conversation_llm_calls',
        'omi_shaped_agent_input_tokens',
    ):
        assert not _kept(name, relabels), name
    assert not _kept('omi_fallback_total', relabels, component='stt_live_session')
    assert _kept('omi_fallback_total', relabels, component='sync')


def test_service_identity_and_sample_ceiling_are_preserved():
    config = yaml.safe_load(SYNC_PROFILE.read_text(encoding='utf-8'))
    endpoint = config['spec']['endpoints'][0]
    # Service identity: the collector stamps the Cloud Run service on every sample.
    assert config['spec']['targetLabels'] == {'metadata': ['service']}
    assert endpoint['interval'] == '60s'
    # GMP drops the whole scrape above the ceiling; the addition must fit inside it.
    assert config['spec']['limits'] == {
        'samples': 15000,
        'labels': 30,
        'labelNameLength': 100,
        'labelValueLength': 256,
    }


def test_added_family_cardinality_fits_the_existing_ceiling():
    """Worst-case series bound for the added families, from the emitters' closed enums.

    Assumptions: ``omi_conversation_llm_calls_total`` is bounded by
    ``LLM_FEATURES`` x {completed, failed, other}; ``omi_shaped_agent_input_tokens_total``
    by the low-cardinality ``Mount.feature`` literals (measured ~10, capped at 20)
    x {cached, uncached}; ``omi_episode_moment_updates_total`` by
    ``MOMENT_TRIGGERS`` x ``MOMENT_OUTCOMES``; every notes-agent counter label is a
    closed enum capped at 12 values and every notes-agent histogram at its bucket
    count + 2. The bound stays far below the 15000-sample ceiling, so no ceiling
    change is needed.
    """
    from utils.episodes.metrics import MOMENT_OUTCOMES, MOMENT_TRIGGERS
    from utils.sync.repeat_work_metrics import LLM_FEATURES

    conversation_calls = len(LLM_FEATURES) * 3
    shaped_tokens = 20 * 2
    notes_counters = 9 * 12
    notes_histograms = (8 + 2) + (7 + 2) + (10 + 2) + (11 + 2) + (10 + 2)
    episode_moment = len(MOMENT_TRIGGERS) * len(MOMENT_OUTCOMES) + 2 + 1
    bound = conversation_calls + shaped_tokens + notes_counters + notes_histograms + episode_moment
    assert bound <= 500, bound
    assert bound < 15000
