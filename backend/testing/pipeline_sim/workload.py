"""Seeded synthetic workload: owners, Poisson uploads, bursts and edge cases.

Every identity is synthetic (``sim-owner-N``); no audio, transcript or user
data exists anywhere in the simulation. Segment content is a single label:
``speech``, ``near_silence`` (VAD fires, ASR often empty) or ``silence``.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from testing.pipeline_sim.stt import NEAR_SILENCE, SILENCE, SPEECH

NORMAL = 'normal'
BURST = 'burst'
PRIVACY_AT_ADMISSION = 'privacy_blocked_at_admission'
PRIVACY_MIDFLIGHT = 'privacy_blocked_midflight'

TARGET_LIVE = 'live'
TARGET_MERGED = 'merged'
TARGET_DELETED = 'deleted'


@dataclass(frozen=True)
class SegmentSpec:
    index: int
    duration: float
    kind: str


@dataclass(frozen=True)
class UploadSpec:
    upload_id: str
    owner: str
    owner_kind: str
    at: float  # seconds after simulation start
    recording_age: float
    content_id: str
    segments: tuple[SegmentSpec, ...]
    lane: str = 'fresh'
    target: str | None = None  # None: capture spans; else finalize target state
    duplicate_of: str | None = None


@dataclass
class WorkloadSpec:
    owners: int = 30
    uploads_per_owner_per_hour: float = 2.0
    arrival_seconds: float = 3600.0
    segments_per_upload: tuple[int, int] = (1, 3)
    speech_seconds: tuple[float, float] = (60.0, 600.0)
    near_silence_fraction: float = 0.04
    near_silence_seconds: tuple[float, float] = (4.0, 12.0)
    silence_fraction: float = 0.05
    burst_owners: int = 0
    burst_uploads: int = 365
    burst_at: float = 60.0
    burst_segment_seconds: tuple[float, float] = (30.0, 120.0)
    burst_lane: str = 'backfill'
    live_target_fraction: float = 0.0
    merged_target_fraction: float = 0.0
    deleted_target_fraction: float = 0.0
    retarget_delay_seconds: tuple[float, float] = (1.0, 30.0)  # merge/delete lands while the work is in flight
    privacy_blocked_owners: int = 0
    privacy_midflight_owners: int = 0
    privacy_midflight_at: float = 600.0
    duplicate_upload_fraction: float = 0.0
    duplicate_delay_seconds: tuple[float, float] = (1.0, 120.0)


@dataclass
class Workload:
    spec: WorkloadSpec
    owners: dict[str, str] = field(default_factory=dict)
    uploads: list[UploadSpec] = field(default_factory=list)


def content_id_for(upload_id: str) -> str:
    return hashlib.sha256(f'sim-content:{upload_id}'.encode()).hexdigest()[:40]


def _segment(rng: random.Random, spec: WorkloadSpec, index: int, *, speech_range=None) -> SegmentSpec:
    draw = rng.random()
    if draw < spec.silence_fraction:
        return SegmentSpec(index, round(rng.uniform(*spec.near_silence_seconds), 2), SILENCE)
    if draw < spec.silence_fraction + spec.near_silence_fraction:
        return SegmentSpec(index, round(rng.uniform(*spec.near_silence_seconds), 2), NEAR_SILENCE)
    return SegmentSpec(index, round(rng.uniform(*(speech_range or spec.speech_seconds)), 2), SPEECH)


def generate(spec: WorkloadSpec, rng: random.Random) -> Workload:
    workload = Workload(spec)
    kinds = (
        [PRIVACY_AT_ADMISSION] * spec.privacy_blocked_owners
        + [PRIVACY_MIDFLIGHT] * spec.privacy_midflight_owners
        + [BURST] * spec.burst_owners
    )
    kinds += [NORMAL] * max(0, spec.owners - len(kinds))
    counter = 0
    for number, kind in enumerate(kinds):
        owner = f'sim-owner-{number:04d}'
        workload.owners[owner] = kind
        if kind == BURST:
            for n in range(spec.burst_uploads):
                upload_id = f'u{counter:06d}'
                counter += 1
                workload.uploads.append(
                    UploadSpec(
                        upload_id,
                        owner,
                        kind,
                        spec.burst_at + n * 0.01,
                        recording_age=86400.0 + (spec.burst_uploads - n) * 600.0,
                        content_id=content_id_for(upload_id),
                        segments=(_segment(rng, spec, 0, speech_range=spec.burst_segment_seconds),),
                        lane=spec.burst_lane,
                    )
                )
            continue
        rate = spec.uploads_per_owner_per_hour / 3600.0
        at = rng.expovariate(rate) if rate > 0 else spec.arrival_seconds
        while at < spec.arrival_seconds:
            upload_id = f'u{counter:06d}'
            counter += 1
            count = rng.randint(*spec.segments_per_upload)
            draw = rng.random()
            target = None
            if draw < spec.deleted_target_fraction:
                target = TARGET_DELETED
            elif draw < spec.deleted_target_fraction + spec.merged_target_fraction:
                target = TARGET_MERGED
            elif draw < spec.deleted_target_fraction + spec.merged_target_fraction + spec.live_target_fraction:
                target = TARGET_LIVE
            upload = UploadSpec(
                upload_id,
                owner,
                kind,
                round(at, 3),
                recording_age=rng.uniform(30.0, 1800.0),
                content_id=content_id_for(upload_id),
                segments=tuple(_segment(rng, spec, index) for index in range(count)),
                target=target,
            )
            workload.uploads.append(upload)
            if rng.random() < spec.duplicate_upload_fraction:
                # Sync/live overlap: the same content arrives again (same content ID).
                workload.uploads.append(
                    UploadSpec(
                        f'{upload_id}-dup',
                        owner,
                        kind,
                        round(at + rng.uniform(*spec.duplicate_delay_seconds), 3),
                        upload.recording_age,
                        upload.content_id,
                        upload.segments,
                        target=target,
                        duplicate_of=upload_id,
                    )
                )
            at += rng.expovariate(rate)
    workload.uploads.sort(key=lambda upload: (upload.at, upload.upload_id))
    return workload
