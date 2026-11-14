"""Named, parameterized scenarios. Each returns a ``SimConfig``; ``run`` scores it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from testing.pipeline_sim.backlog_flood import run_backlog_flood
from testing.pipeline_sim.scorer import score
from testing.pipeline_sim.sim import SimConfig, simulate
from testing.pipeline_sim.stt import ExhaustionWindow, ModulateProfile, STTProfile
from testing.pipeline_sim.workload import WorkloadSpec


def burst_owner_serial_sequencer(
    seed: int = 1, *, per_owner_concurrency: int = 1, burst_uploads: int = 365
) -> SimConfig:
    """One owner uploads ``burst_uploads`` historical captures at once (legacy sequenced backfill lane).

    Production keeps one in-flight backfill job per UID, so the burst drains
    serially; ``per_owner_concurrency`` is the hypothetical K to compare.
    """
    return SimConfig(
        name='burst_owner_serial_sequencer',
        seed=seed,
        path='legacy',
        workload=WorkloadSpec(
            owners=8,
            uploads_per_owner_per_hour=2.0,
            arrival_seconds=1800.0,
            burst_owners=1,
            burst_uploads=burst_uploads,
            burst_at=60.0,
        ),
        stt=STTProfile(min_replicas=4, max_replicas=8),
        sequencer_per_owner_concurrency=per_owner_concurrency,
        horizon_seconds=4 * 3600.0,
    )


def mixed_fleet_steady(seed: int = 1, *, owners: int = 40) -> SimConfig:
    """Healthy baseline on the real batch state machine: should pass every gate."""
    return SimConfig(
        name='mixed_fleet_steady',
        seed=seed,
        workload=WorkloadSpec(owners=owners, uploads_per_owner_per_hour=2.0, arrival_seconds=3600.0),
        stt=STTProfile(min_replicas=2, max_replicas=6),
        horizon_seconds=3 * 3600.0,
    )


def provider_exhaustion_window(
    seed: int = 1, *, start: float = 900.0, minutes: float = 30.0, mode: str = 'empty', owners: int = 60
) -> SimConfig:
    """ASR fleet pinned at HPA max returning empty results for a window -> empty_asr quarantines -> paid recovery."""
    return SimConfig(
        name='provider_exhaustion_window',
        seed=seed,
        workload=WorkloadSpec(owners=owners, uploads_per_owner_per_hour=2.0, arrival_seconds=3600.0),
        stt=STTProfile(
            min_replicas=6,
            max_replicas=6,
            exhaustion=(ExhaustionWindow(start, start + minutes * 60.0, mode),),
        ),
        # Hold one fixed input; latency comparisons must not depend on which
        # random paid-provider failures a different polling order draws.
        unrecoverable_near_silence=True,
        modulate=ModulateProfile(speech_recover_rate=1.0, near_silence_recover_rate=1.0),
        horizon_seconds=4 * 3600.0,
    )


def revision_replacement_mid_run(
    seed: int = 1, *, summary_dispatch: str = 'background', at: float = 1500.0
) -> SimConfig:
    """CPU revision replaced mid-run (GPU pumps SIGTERMed too): un-awaited work is lost, awaited/durable survives."""
    return SimConfig(
        name='revision_replacement_mid_run',
        seed=seed,
        workload=WorkloadSpec(
            owners=120, uploads_per_owner_per_hour=3.0, arrival_seconds=3600.0, near_silence_fraction=0.08
        ),
        stt=STTProfile(min_replicas=6, max_replicas=10),
        summary_dispatch=summary_dispatch,
        summary_seconds=45.0,
        summary_sigma=0.25,
        revision_replacement_at=at,
        horizon_seconds=3 * 3600.0,
    )


def stale_finalize_targets(seed: int = 1) -> SimConfig:
    """Finalize targets merged (redirect) or deleted after admission: not failures, no paid calls after the fence."""
    return SimConfig(
        name='stale_finalize_targets',
        seed=seed,
        workload=WorkloadSpec(
            owners=30,
            uploads_per_owner_per_hour=2.0,
            arrival_seconds=3600.0,
            merged_target_fraction=0.15,
            deleted_target_fraction=0.15,
            near_silence_fraction=0.08,
            duplicate_upload_fraction=0.1,
        ),
        recovery_duplicate_delivery_rate=0.5,
        worker_rpc_duplicate_rate=0.3,
        unrecoverable_near_silence=True,
        modulate=ModulateProfile(speech_recover_rate=1.0, near_silence_recover_rate=1.0),
        horizon_seconds=3 * 3600.0,
    )


def privacy_blocked_users(seed: int = 1) -> SimConfig:
    """Owners blocked before admission (409) and mid-flight: no paid calls, no projection, reported distinctly."""
    return SimConfig(
        name='privacy_blocked_users',
        seed=seed,
        workload=WorkloadSpec(
            owners=30,
            uploads_per_owner_per_hour=3.0,
            arrival_seconds=3600.0,
            near_silence_fraction=0.04,
            privacy_blocked_owners=3,
            privacy_midflight_owners=3,
            privacy_midflight_at=900.0,
        ),
        # Quarantines pile up just before the fence so some recoveries are still queued when it lands.
        stt=STTProfile(min_replicas=4, max_replicas=4, exhaustion=(ExhaustionWindow(600.0, 900.0, 'empty'),)),
        horizon_seconds=3 * 3600.0,
    )


def backlog_flood_fresh_latency(
    seed: int = 1,
    *,
    release: str = 'held',
    flood: bool = True,
    owner_drain_first_turn_seconds: int = 15,
) -> SimConfig:
    """A 22x-hourly, already-transcribed flood must not delay steady fresh captures."""
    if release not in {'held', 'unmetered', 'gated'}:
        raise ValueError("release must be 'held', 'unmetered', or reserved 'gated'")
    if owner_drain_first_turn_seconds not in {0, 15}:
        raise ValueError('projection switch is tested at its main defaults: 0 (off) or 15 (on)')
    return SimConfig(
        name='backlog_flood_fresh_latency',
        seed=seed,
        workload=WorkloadSpec(
            owners=80,
            uploads_per_owner_per_hour=0.0,
            arrival_seconds=3600.0,
            segments_per_upload=(1, 1),
            speech_seconds=(30.0, 30.0),
            near_silence_fraction=0.0,
            silence_fraction=0.0,
        ),
        # Provider delivery is deliberately quick; backlog projection, not STT capacity, is the bottleneck.
        modulate=ModulateProfile(
            concurrency=64,
            base_latency_seconds=1.0,
            seconds_per_audio_second=0.01,
            speech_recover_rate=1.0,
        ),
        summary_dispatch='task',
        summary_pool='isolated',
        summary_seconds=0.1,
        summary_sigma=0.0,
        projection_seconds=1.0,
        # Every fresh row is provider-routed and every old row is already transcribed; one pump
        # retains the real idle/maintenance path without duplicating irrelevant GPU polling work.
        gpu_pumps=1,
        horizon_seconds=2 * 3600.0,
        gate_poll_seconds=10**9,  # This scenario has a fresh-cohort verdict, not the whole-fleet gate.
        language='ja',
        legacy_sync='draining',
        flags={
            'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED': 'true',
            'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED': str(release == 'unmetered').lower(),
            # The unmetered arm characterizes rollback to the legacy release path.
            'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED': str(release != 'unmetered').lower(),
            'BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS': '60',
            'BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH': '0' if release == 'unmetered' else '16',
            'BATCH_PIPELINE_MAX_OWNER_DRAINS': '8',
            'BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS': str(owner_drain_first_turn_seconds),
            'BATCH_PIPELINE_PROJECTION_RECENT_DISCOVERY_SECONDS': '120',
        },
        backlog_flood={
            'release': release,
            'flood': flood,
            'flood_at': 600.0,
            'fresh_owners': 60,
            'steady_uploads_per_owner': 6,
            'fresh_interval_seconds': 600.0,
            'flooded_owners': 30,
            'fresh_flooded_owners': 10,
            'rows_per_flooded_owner': 264,
            'catch_up_depth': 0 if release == 'unmetered' else 16,
            'first_turn_seconds': owner_drain_first_turn_seconds,
        },
    )


def summary_behind_transcription(seed: int = 1, *, summary_pool: str = 'shared') -> SimConfig:
    """Legacy sync path: first summaries share sync_executor (16 threads) with blocking transcription."""
    return SimConfig(
        name='summary_behind_transcription',
        seed=seed,
        path='legacy',
        workload=WorkloadSpec(
            owners=300, uploads_per_owner_per_hour=3.0, arrival_seconds=3600.0, segments_per_upload=(2, 5)
        ),
        stt=STTProfile(min_replicas=6, max_replicas=10, seconds_per_audio_second=0.04),
        modulate=ModulateProfile(),
        summary_pool=summary_pool,
        horizon_seconds=3 * 3600.0,
    )


SCENARIOS: dict[str, Callable[..., SimConfig]] = {
    'burst_owner_serial_sequencer': burst_owner_serial_sequencer,
    'mixed_fleet_steady': mixed_fleet_steady,
    'provider_exhaustion_window': provider_exhaustion_window,
    'revision_replacement_mid_run': revision_replacement_mid_run,
    'stale_finalize_targets': stale_finalize_targets,
    'privacy_blocked_users': privacy_blocked_users,
    'summary_behind_transcription': summary_behind_transcription,
    'backlog_flood_fresh_latency': backlog_flood_fresh_latency,
}


def run(name: str, seed: int = 1, *, overrides: dict[str, Any] | None = None, **params: Any) -> dict[str, Any]:
    config = SCENARIOS[name](seed, **params)
    if overrides:
        config = replace(config, **overrides)
    if config.backlog_flood is not None:
        return run_backlog_flood(config)
    return score(simulate(config))
