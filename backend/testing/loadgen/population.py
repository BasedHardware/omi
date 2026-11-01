"""Deterministic synthetic population for staging replay (swarm lane 4, plan F F7).

A *recording* is an ordered run of source files (David's mirrored audio, or
synthetic fixtures). The generator deals recordings to pseudo-owners and
plans their uploads:

- **steady** owners upload recent audio (fresh lane) at the profile's
  hour-of-day rate;
- **burst** owners upload an 8-10-day-old backlog back to back (backfill);
- **reverse** owners upload a backlog newest-first (the 10-19 02:45Z
  ordered-head shape);
- **shuffled** owners upload a backlog in random order.

Capture times are stored relative to the send instant (``capture_offset_s``,
always negative), so filenames are minted at send time and are never in the
future however late a replay starts. Silence is varied per file (lead/trail
pads) and whole near-silent files are interleaved at the profile's rate.

The plan is pure data (JSON lines); ``scripts/staging/replay.py`` sends it.
No IO at import time; generation is a pure function of its inputs and seed.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

PLAN_SCHEMA_VERSION = 1
FRESH_MAX_AGE_S = 6 * 3600  # utils/sync/lanes.py fresh_cutoff_seconds default
OWNER_PREFIX = 'lg'


class OwnerShape(str, Enum):
    STEADY = 'steady'
    BURST = 'burst'
    REVERSE = 'reverse'
    SHUFFLED = 'shuffled'


@dataclass(frozen=True)
class SourceFile:
    ref: str  # 'mirror:<object name>' | 'synthetic:<kind>:<n>'
    source_format: str  # testing.loadgen.mirror_codec.SOURCE_FORMATS
    duration_s: float
    capture_start: float  # original capture epoch seconds (only its spacing is used)
    original_name: str = ''  # raw uploads keep the device filename for codec fields


@dataclass(frozen=True)
class Recording:
    key: str  # opaque group label (keyed hash for mirror sources)
    files: tuple[SourceFile, ...]

    @property
    def span_s(self) -> float:
        if not self.files:
            return 0.0
        first = self.files[0]
        last = self.files[-1]
        return max(0.0, last.capture_start + last.duration_s - first.capture_start)


@dataclass(frozen=True)
class PlannedFile:
    ref: str
    source_format: str
    original_name: str
    capture_offset_s: float  # capture start minus send time (negative)
    duration_s: float
    lead_silence_s: float = 0.0
    trail_silence_s: float = 0.0
    silent_only: bool = False  # a near-silent file synthesized in the same codec


@dataclass(frozen=True)
class PlannedUpload:
    at_s: float  # earliest send offset from replay start; owners send serially
    owner_id: str
    shape: str
    recording_key: str
    sequence: int  # per-owner send order
    lane_hint: str  # 'fresh' | 'backfill' (expected classification at send time)
    platform: str
    device_hash: str
    files: tuple[PlannedFile, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))

    @staticmethod
    def from_json(line: str) -> 'PlannedUpload':
        raw = json.loads(line)
        raw['files'] = tuple(PlannedFile(**f) for f in raw['files'])
        return PlannedUpload(**raw)


@dataclass(frozen=True)
class PopulationSpec:
    run_id: str
    owners: int = 50
    duration_s: float = 2 * 3600
    rate_per_min: float | None = None  # total upload rate; None = percent_of_prod x profile
    percent_of_prod: float = 1.0
    shape_mix: dict[str, float] = field(
        default_factory=lambda: {'steady': 0.7, 'burst': 0.1, 'reverse': 0.1, 'shuffled': 0.1}
    )
    # None = derived so backlog uploads match the profile's backfill share of the rate;
    # a burst owner carries ``burst_intensity`` times a reverse/shuffled owner's backlog.
    burst_backlog_recordings: int | None = None
    backlog_recordings: int | None = None
    burst_intensity: float = 3.0
    silence_pad_fraction: float = 0.3
    silence_pad_max_s: float = 30.0
    seed: int = 1
    start_utc_hour: int | None = None  # aligns the hour-of-day curve; None = flat


def owner_id(run_id: str, index: int) -> str:
    """Pseudo-owner uid: obviously synthetic, stable per run, never a real uid shape."""
    if not run_id or not run_id.replace('-', '').isalnum() or len(run_id) > 24:
        raise ValueError('run_id must be a short alphanumeric/dash label')
    return f'{OWNER_PREFIX}-{run_id}-o{index:04d}'


def _allocate(total: int, mix: dict[str, float]) -> list[str]:
    """Exact largest-remainder allocation of owner shapes, in a stable order."""
    shapes = [s for s in (o.value for o in OwnerShape) if mix.get(s, 0) > 0]
    weight = sum(mix[s] for s in shapes)
    if total <= 0 or weight <= 0:
        return []
    quotas = {s: total * mix[s] / weight for s in shapes}
    counts = {s: int(quotas[s]) for s in shapes}
    remainder = total - sum(counts.values())
    for s in sorted(shapes, key=lambda s: (quotas[s] - counts[s], s), reverse=True)[:remainder]:
        counts[s] += 1
    return [s for s in shapes for _ in range(counts[s])]


def _weighted_int(rng: random.Random, weights: dict[str, float]) -> int:
    keys = sorted(weights, key=int)
    return int(rng.choices(keys, weights=[weights[k] for k in keys])[0])


def _sample_age(rng: random.Random, age: dict[str, list[float]] | None, lo: float, hi: float) -> float:
    """Sample a recording age from a cumulative histogram, clamped to [lo, hi]."""
    if not age or not age.get('le'):
        return rng.uniform(lo, hi)
    u = rng.random()
    prev_le, prev_cdf = 0.0, 0.0
    for le, cdf in zip(age['le'], age['cdf']):
        if u <= cdf:
            span = max(cdf - prev_cdf, 1e-9)
            value = prev_le + (le - prev_le) * (u - prev_cdf) / span
            return min(max(value, lo), hi)
        prev_le, prev_cdf = le, cdf
    return min(max(prev_le, lo), hi)


def _hour_weight(profile: dict[str, Any], spec: PopulationSpec, at_s: float) -> float:
    curve = (profile.get('uploads') or {}).get('accepted_per_min_by_utc_hour') or []
    if spec.start_utc_hour is None or len(curve) != 24 or not any(curve):
        return 1.0
    peak = max(curve)
    return curve[int(spec.start_utc_hour + at_s // 3600) % 24] / peak


def _window_weights(profile: dict[str, Any], spec: PopulationSpec) -> tuple[float, float]:
    """(level, thinning) over the run window, sampled per minute.

    ``level`` scales the daily-mean rate to the window's hours (curve / daily mean), so backlog
    and steady uploads share one window total. ``thinning`` is the mean acceptance of the steady
    Poisson thinning (curve / peak); the steady rate is divided by it so thinning keeps the
    steady share instead of shrinking it (the 10-19 m1p1 plan had 57% backfill vs 39%)."""
    curve = (profile.get('uploads') or {}).get('accepted_per_min_by_utc_hour') or []
    if spec.start_utc_hour is None or len(curve) != 24 or not any(curve):
        return 1.0, 1.0
    daily_mean = sum(curve) / 24.0
    minutes = max(1, int(spec.duration_s // 60))
    hours = [curve[int(spec.start_utc_hour + (m * 60) // 3600) % 24] for m in range(minutes)]
    return sum(hours) / minutes / daily_mean, sum(hours) / minutes / max(curve)


def total_rate_per_min(spec: PopulationSpec, profile: dict[str, Any]) -> float:
    if spec.rate_per_min is not None:
        return spec.rate_per_min
    prod = float((profile.get('uploads') or {}).get('accepted_per_min_mean') or 0.0)
    if prod <= 0:
        raise ValueError('profile has no prod upload rate; pass rate_per_min')
    return prod * spec.percent_of_prod / 100.0


def _platform_and_device(rng: random.Random, profile: dict[str, Any], owner: str) -> tuple[str, str]:
    mix = {k: v for k, v in (profile.get('platform_mix') or {'ios': 1.0}).items() if k in ('ios', 'android')}
    platform = rng.choices(sorted(mix), weights=[mix[k] for k in sorted(mix)])[0] if mix else 'ios'
    # utils.client_device.build_client_device_id accepts exactly 8 hex characters; any other width
    # resolves to no device, so every "fresh" upload would be admitted as untrusted backfill.
    return platform, hashlib.sha256(f'device:{owner}'.encode()).hexdigest()[:8]


def _split_uploads(
    rng: random.Random, recording: Recording, files_weights: dict[str, float]
) -> list[tuple[SourceFile, ...]]:
    """Cut one recording into upload requests of profile-shaped file counts."""
    out: list[tuple[SourceFile, ...]] = []
    files = list(recording.files)
    while files:
        take = max(1, _weighted_int(rng, files_weights)) if files_weights else len(files)
        out.append(tuple(files[:take]))
        files = files[take:]
    return out


def _plan_files(
    rng: random.Random,
    batch: Sequence[SourceFile],
    capture_base: float,
    origin: float,
    spec: PopulationSpec,
    silent_rate: float,
) -> tuple[PlannedFile, ...]:
    """Place a batch at ``capture_base`` (offset from send), preserving intra-recording spacing."""
    planned: list[PlannedFile] = []
    shift = 0.0
    for f in batch:
        lead = trail = 0.0
        if rng.random() < spec.silence_pad_fraction:
            lead = round(rng.uniform(0, spec.silence_pad_max_s), 1)
            trail = round(rng.uniform(0, spec.silence_pad_max_s), 1)
        offset = capture_base + (f.capture_start - origin) + shift
        planned.append(
            PlannedFile(f.ref, f.source_format, f.original_name, round(offset, 3), f.duration_s, lead, trail)
        )
        shift += lead + trail
        if rng.random() < silent_rate:
            silent_len = round(rng.uniform(5.0, 60.0), 1)
            end = offset + f.duration_s + lead + trail
            planned.append(
                PlannedFile(f.ref, f.source_format, f.original_name, round(end, 3), silent_len, silent_only=True)
            )
            shift += silent_len
    # Pads and interleaved silence must never push a capture past the send instant.
    overrun = max(f.capture_offset_s + f.duration_s + f.lead_silence_s + f.trail_silence_s for f in planned) + 1.0
    if overrun > 0:
        planned = [
            PlannedFile(
                f.ref,
                f.source_format,
                f.original_name,
                round(f.capture_offset_s - overrun, 3),
                f.duration_s,
                f.lead_silence_s,
                f.trail_silence_s,
                f.silent_only,
            )
            for f in planned
        ]
    return tuple(planned)


def backfill_share(profile: dict[str, Any]) -> float:
    lanes = profile.get('lane_decisions') or {}
    total = sum(lanes.values())
    return sum(v for k, v in lanes.items() if k.startswith('backfill/')) / total if total else 0.4


def _backlog_sizes(
    spec: PopulationSpec,
    profile: dict[str, Any],
    shapes: Sequence[str],
    recordings: Sequence[Recording],
    files_weights: dict[str, float],
    rate: float,
) -> tuple[int, int]:
    """Recordings per burst owner and per reverse/shuffled owner."""
    if spec.burst_backlog_recordings is not None and spec.backlog_recordings is not None:
        return spec.burst_backlog_recordings, spec.backlog_recordings
    probe = random.Random(f'{spec.run_id}:{spec.seed}:probe')
    sample = [recordings[i % len(recordings)] for i in range(min(len(recordings), 64))]
    per_recording = sum(len(_split_uploads(probe, r, files_weights)) for r in sample) / len(sample)
    target_uploads = rate * spec.duration_s / 60.0 * backfill_share(profile)
    burst = sum(1 for s in shapes if s == OwnerShape.BURST.value)
    other = sum(1 for s in shapes if s in (OwnerShape.REVERSE.value, OwnerShape.SHUFFLED.value))
    weight = burst * spec.burst_intensity + other
    per_unit = target_uploads / per_recording / weight if weight else 0.0
    burst_n = spec.burst_backlog_recordings
    other_n = spec.backlog_recordings
    if burst_n is None:
        burst_n = max(1, round(per_unit * spec.burst_intensity))
    if other_n is None:
        other_n = max(1, round(per_unit))
    return burst_n, other_n


def generate(recordings: Sequence[Recording], profile: dict[str, Any], spec: PopulationSpec) -> list[PlannedUpload]:
    """Plan every upload for the run, sorted by earliest send time."""
    usable = [r for r in recordings if r.files]
    if not usable:
        raise ValueError('population needs at least one non-empty recording')
    rng = random.Random(f'{spec.run_id}:{spec.seed}')
    assumed = profile.get('assumed') or {}
    files_weights = (assumed.get('files_per_upload') or {}).get('weights') or {'1': 1.0}
    silent_rate = float((assumed.get('near_silence_empty_asr_rate') or {}).get('value') or 0.0) * 0.25
    burst_age = (assumed.get('burst_owners') or {}).get('audio_age_days') or [8, 10]
    ages = profile.get('recording_age_seconds') or {}

    shapes = _allocate(spec.owners, spec.shape_mix)
    rng.shuffle(shapes)
    pool = list(usable)
    rng.shuffle(pool)
    cursor = 0

    used: dict[str, set[str]] = {}

    def deal(owner: str, n: int) -> list[Recording]:
        """Round-robin over the pool; an owner never gets the same recording twice
        while unused ones remain (identical bytes would hit the content ledger)."""
        nonlocal cursor
        seen = used.setdefault(owner, set())
        out = []
        for _ in range(n):
            pick = pool[cursor % len(pool)]
            for probe in range(len(pool)):
                candidate = pool[(cursor + probe) % len(pool)]
                if candidate.key not in seen:
                    pick = candidate
                    cursor += probe
                    break
            cursor += 1
            seen.add(pick.key)
            out.append(pick)
        return out

    steady_owners = [i for i, s in enumerate(shapes) if s == OwnerShape.STEADY.value]
    level, thinning = _window_weights(profile, spec)
    rate = total_rate_per_min(spec, profile) * level
    burst_n, other_n = _backlog_sizes(spec, profile, shapes, usable, files_weights, rate)
    backlog_uploads = 0
    plans: list[PlannedUpload] = []

    for index, shape in enumerate(shapes):
        owner = owner_id(spec.run_id, index)
        platform, device = _platform_and_device(rng, profile, owner)
        if shape == OwnerShape.STEADY.value:
            continue
        count = burst_n if shape == OwnerShape.BURST.value else other_n
        backlog = deal(owner, count)
        if shape == OwnerShape.BURST.value:
            age_lo, age_hi = burst_age[0] * 86400.0, burst_age[1] * 86400.0
        else:
            age_lo, age_hi = FRESH_MAX_AGE_S + 600.0, 3 * 86400.0
        # Lay the backlog out oldest -> newest in capture time, then choose send order.
        newest_age = _sample_age(rng, ages.get('backfill'), age_lo, age_hi)
        timeline: list[tuple[Recording, float]] = []
        age = newest_age + sum(r.span_s + 300.0 for r in backlog)
        for rec in backlog:
            timeline.append((rec, age))
            age -= rec.span_s + 300.0
        if shape == OwnerShape.REVERSE.value:
            order = list(reversed(timeline))
        elif shape == OwnerShape.SHUFFLED.value:
            order = list(timeline)
            rng.shuffle(order)
        else:
            order = timeline
        start = rng.uniform(0, spec.duration_s * 0.5)
        sequence = 0
        for rec, rec_age in order:
            batches = _split_uploads(rng, rec, files_weights)
            if shape == OwnerShape.REVERSE.value:
                batches = list(reversed(batches))
            origin = rec.files[0].capture_start
            for batch in batches:
                files = _plan_files(rng, batch, -rec_age, origin, spec, silent_rate)
                plans.append(
                    PlannedUpload(round(start, 3), owner, shape, rec.key, sequence, 'backfill', platform, device, files)
                )
                sequence += 1
                backlog_uploads += 1

    # Steady owners carry the remaining rate as fresh uploads (thinned Poisson).
    steady_budget = max(0.0, rate * spec.duration_s / 60.0 - backlog_uploads)
    if steady_owners and steady_budget > 0:
        per_owner_rate = steady_budget / len(steady_owners) / spec.duration_s / thinning  # uploads/s, pre-thinning
        for index in steady_owners:
            owner = owner_id(spec.run_id, index)
            platform, device = _platform_and_device(rng, profile, owner)
            t, sequence = 0.0, 0
            while True:
                t += rng.expovariate(per_owner_rate)
                if t >= spec.duration_s:
                    break
                if rng.random() > _hour_weight(profile, spec, t):
                    continue
                rec = deal(owner, 1)[0]
                batch = _split_uploads(rng, rec, files_weights)[0]
                # Fresh: the batch ended a profile-shaped moment before the send.
                end_age = _sample_age(rng, ages.get('fresh'), 30.0, FRESH_MAX_AGE_S - 600.0)
                origin = batch[0].capture_start
                span = batch[-1].capture_start + batch[-1].duration_s - origin
                files = _plan_files(rng, batch, -(end_age + span), origin, spec, silent_rate)
                plans.append(
                    PlannedUpload(
                        round(t, 3), owner, OwnerShape.STEADY.value, rec.key, sequence, 'fresh', platform, device, files
                    )
                )
                sequence += 1

    plans.sort(key=lambda p: (p.at_s, p.owner_id, p.sequence))
    return plans


def burst_spec(run_id: str, owners: int, *, recordings_per_owner: int = 12, seed: int = 1) -> PopulationSpec:
    """N-owner burst at full per-owner intensity (swarm M2): every owner is a burst owner."""
    return PopulationSpec(
        run_id=run_id,
        owners=owners,
        duration_s=3600.0,
        rate_per_min=0.0,
        shape_mix={'burst': 1.0},
        burst_backlog_recordings=recordings_per_owner,
        seed=seed,
    )


def summarize(plans: Iterable[PlannedUpload]) -> dict[str, Any]:
    plans = list(plans)
    owners = {p.owner_id for p in plans}
    by_shape: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    files = silent = 0
    audio_s = 0.0
    for p in plans:
        by_shape[p.shape] = by_shape.get(p.shape, 0) + 1
        by_lane[p.lane_hint] = by_lane.get(p.lane_hint, 0) + 1
        files += len(p.files)
        silent += sum(1 for f in p.files if f.silent_only)
        audio_s += sum(f.duration_s + f.lead_silence_s + f.trail_silence_s for f in p.files)
    return {
        'uploads': len(plans),
        'owners': len(owners),
        'files': files,
        'silent_files': silent,
        'audio_hours': round(audio_s / 3600.0, 3),
        'uploads_by_shape': dict(sorted(by_shape.items())),
        'uploads_by_lane': dict(sorted(by_lane.items())),
        'last_send_s': max((p.at_s for p in plans), default=0.0),
    }


def write_plan(path: str, plans: Sequence[PlannedUpload], spec: PopulationSpec) -> None:
    header = {'schema_version': PLAN_SCHEMA_VERSION, 'spec': asdict(spec), 'summary': summarize(plans)}
    with open(path, 'w', encoding='utf-8') as out:
        out.write(json.dumps({'header': header}, sort_keys=True) + '\n')
        for p in plans:
            out.write(p.to_json() + '\n')


def read_plan(path: str) -> tuple[dict[str, Any], list[PlannedUpload]]:
    with open(path, encoding='utf-8') as handle:
        lines = [line for line in handle if line.strip()]
    header = json.loads(lines[0]).get('header') or {}
    if header.get('schema_version') != PLAN_SCHEMA_VERSION:
        raise ValueError('unsupported population plan schema')
    return header, [PlannedUpload.from_json(line) for line in lines[1:]]


def synthetic_recordings(count: int, *, files_per_recording: int = 3, file_seconds: float = 60.0) -> list[Recording]:
    """Fixture recordings for hermetic tests and emulator runs (tone/silence synthesized at send)."""
    recordings = []
    for r in range(count):
        files = tuple(
            SourceFile(f'synthetic:tone:{r}:{i}', 'chunk-pcm16', file_seconds, 1_760_000_000.0 + i * file_seconds)
            for i in range(files_per_recording)
        )
        recordings.append(Recording(hashlib.sha256(f'synthetic:{r}'.encode()).hexdigest()[:32], files))
    return recordings


def recordings_from_manifest(manifest: dict[str, Any]) -> list[Recording]:
    """Mirror manifest (scripts/staging/mirror_owner_recordings.py) -> recordings."""
    groups: dict[str, list[SourceFile]] = {}
    for obj in manifest.get('objects', []):
        groups.setdefault(obj['group'], []).append(
            SourceFile(
                f"mirror:{obj['object']}",
                obj['source_format'],
                float(obj['duration_s']),
                float(obj['capture_start']),
                obj.get('original_name', ''),
            )
        )
    return [
        Recording(key, tuple(sorted(files, key=lambda f: f.capture_start))) for key, files in sorted(groups.items())
    ]
