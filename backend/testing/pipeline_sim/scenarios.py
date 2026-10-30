"""Named, parameterized scenarios. Each returns a ``SimConfig``; ``run`` scores it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

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
}


def run(name: str, seed: int = 1, *, overrides: dict[str, Any] | None = None, **params: Any) -> dict[str, Any]:
    config = SCENARIOS[name](seed, **params)
    if overrides:
        config = replace(config, **overrides)
    return score(simulate(config))
