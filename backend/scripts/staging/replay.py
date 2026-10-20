"""Replay a synthetic population into staging through the real upload routes.

Two steps:

    # 1. plan (anywhere; pure, no network)
    python -m scripts.staging.replay plan --run-id r1 --owners 50 --percent-of-prod 1 \\
        --hours 2 --manifest mirror-manifest.json --out plan.jsonl

    # 2. send (m1-mac-studio or in-cluster on staging ONLY; never m5, swarm §8)
    python -m scripts.staging.replay run --plan plan.jsonl \\
        --target https://backend-sync-staging-<hash>.a.run.app --out results/ --poll

Every upload goes through ``POST /v2/sync-local-files`` exactly as a client
sends it (WAL-framed files named ``audio_<device>_<codec>_..._<ts>.bin``),
with ADMIN_KEY impersonation of the plan's pseudo-owners. Fresh-lane uploads
optionally get device-bound capture provenance first (``--seed-capture``),
which writes a server-capture conversation stub through the production encoder
into the staging Firestore DB; that mode refuses to start unless lane 2's
staging fence passes in-process.

Outputs (``--out``): ``results.jsonl`` (one row per upload), ``population.json``
(pseudo-owner ids, shapes, job ids and conversation ids for lane 5's parity
gate) and ``summary.json``. Nothing here logs audio, keys or real uids.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import socket
import sys
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from testing.loadgen import mirror_codec as mc  # noqa: E402
from testing.loadgen import population as pop  # noqa: E402
from testing.loadgen.refresh_profile import PROFILE_PATH, load_profile  # noqa: E402
from utils.client_device import build_client_device_id  # noqa: E402

TERMINAL_STATUSES = frozenset({'completed', 'partial_failure', 'failed'})
STAGING_HOST_RE = re.compile(r'^[a-z0-9-]*staging[a-z0-9-]*\.(a\.)?run\.app$')
LOCAL_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
LOAD_HOSTS = frozenset({'m1-mac-studio'})  # swarm §8: never m5
DEVICE_TOKEN = 'omi'


class ReplayRefused(RuntimeError):
    """A safety precondition failed; nothing was sent."""


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


def check_target(url: str, *, allow_local: bool) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    if 'omi.me' in host or 'based-hardware.' in host:
        raise ReplayRefused('target is a production host')
    if host in LOCAL_HOSTS:
        if not allow_local:
            raise ReplayRefused('local target needs --allow-local (hermetic stack only)')
        return url.rstrip('/')
    if parts.scheme != 'https' or not STAGING_HOST_RE.match(host):
        raise ReplayRefused('target must be an https *-staging-* Cloud Run host')
    return url.rstrip('/')


def check_plan_lanes(plans: list[pop.PlannedUpload], *, seed_capture: bool, unseeded_fresh: bool) -> None:
    """Refuse a plan whose fresh uploads cannot reach the fresh lane.

    The server binds a fresh upload to a device only through ``build_client_device_id`` (8 hex
    characters) plus device-bound capture provenance. Without both, admission files it as untrusted
    backfill and still answers 202, so the run would silently measure the wrong queue (M1 L04-1).
    """
    fresh = [p for p in plans if p.lane_hint == 'fresh']
    if not fresh:
        return
    unbound = sum(1 for p in fresh if build_client_device_id(p.platform, p.device_hash) is None)
    if unbound:
        raise ReplayRefused(
            f'{unbound} fresh uploads carry a device hash the server rejects (8 hex required); regenerate the plan'
        )
    if not seed_capture and not unseeded_fresh:
        raise ReplayRefused(
            f'plan has {len(fresh)} fresh uploads: pass --seed-capture (device-bound provenance), or '
            '--unseeded-fresh only when the target admits legacy fresh (SYNC_LEGACY_FRESH_ENABLED)'
        )


def check_load_host(target: str, env: dict[str, str] | None = None) -> str:
    """Load against staging runs in-cluster or on m1-mac-studio only (swarm §8)."""
    env = dict(os.environ if env is None else env)
    host = (urlsplit(target).hostname or '').lower()
    if host in LOCAL_HOSTS:
        return 'local'
    if env.get('KUBERNETES_SERVICE_HOST'):
        return 'in-cluster'
    declared = env.get('OMI_LOADGEN_HOST', '').strip()
    if declared in LOAD_HOSTS:
        return declared
    raise ReplayRefused(
        f'refusing to generate staging load from {socket.gethostname()!r}: run in-cluster or set '
        f'OMI_LOADGEN_HOST to one of {sorted(LOAD_HOSTS)} on that host'
    )


# --------------------------------------------------------------------------
# Audio sources
# --------------------------------------------------------------------------


class SourceReader(Protocol):
    def read(self, ref: str) -> bytes: ...


def synthetic_pcm(ref: str, seconds: float, *, variant: str) -> bytes:
    """Deterministic speech-band tone bursts with gaps; ``variant`` makes bytes owner-unique."""
    import numpy as np

    samples = int(seconds * mc.PCM_SAMPLE_RATE)
    seed = int(hashlib.sha256(f'{ref}:{variant}'.encode()).hexdigest()[:8], 16)
    freq = 180 + seed % 220
    t = np.arange(samples, dtype=np.float64) / mc.PCM_SAMPLE_RATE
    voiced = ((np.floor(t * 2).astype(np.int64) + seed) % 5) != 0  # 80% voiced, 20% gaps
    pcm = (6000 * np.sin(2 * np.pi * freq * t) * voiced).astype('<i2')
    if samples:
        pcm[0] = seed & 0x7FFF
    return pcm.tobytes()


class MirrorReader:
    """Reads sealed mirror objects; plaintext stays in a bounded in-memory LRU."""

    def __init__(self, bucket: Any, mirror_key: bytes, cache_bytes: int = 512 * 1024 * 1024):
        self.bucket = bucket
        self.key = mirror_key
        self.cache: OrderedDict[str, bytes] = OrderedDict()
        self.cache_bytes = cache_bytes
        self.held = 0

    def read(self, ref: str) -> bytes:
        name = ref.removeprefix('mirror:')
        if name in self.cache:
            self.cache.move_to_end(name)
            return self.cache[name]
        sealed = self.bucket.blob(name).download_as_bytes(timeout=60)
        plain = mc.open_mirror_object(self.key, name, sealed)
        self.cache[name] = plain
        self.held += len(plain)
        while self.held > self.cache_bytes and self.cache:
            _, evicted = self.cache.popitem(last=False)
            self.held -= len(evicted)
        return plain


@dataclass
class Materialized:
    files: list[tuple[str, bytes]]
    audio_s: float
    capture_lo: float
    capture_hi: float


def materialize(
    upload: pop.PlannedUpload,
    send_epoch: float,
    reader: SourceReader | None,
    *,
    opus_silence: bytes | None,
) -> Materialized:
    files: list[tuple[str, bytes]] = []
    audio_s = 0.0
    lo, hi = math.inf, -math.inf
    last_audio: mc.UploadAudio | None = None
    for f in upload.files:
        start = send_epoch + f.capture_offset_s
        if f.silent_only:
            base = last_audio or mc.UploadAudio('pcm16', mc.PCM_SAMPLE_RATE, mc.WAL_PCM_FRAME_SAMPLES, b'', 0.0)
            if base.codec.startswith('opus') and not opus_silence:
                base = mc.UploadAudio('pcm16', mc.PCM_SAMPLE_RATE, mc.WAL_PCM_FRAME_SAMPLES, b'', 0.0)
            body = mc.wal_frame(mc.silence_payloads(base, f.duration_s, opus_silence))
            audio = mc.UploadAudio(base.codec, base.sample_rate, base.frame_size, body, f.duration_s)
        else:
            if f.ref.startswith('synthetic:'):
                plain = synthetic_pcm(f.ref, f.duration_s, variant=upload.owner_id)
                audio = mc.to_upload_audio(mc.FORMAT_CHUNK_PCM16, plain)
            else:
                if reader is None:
                    raise ReplayRefused('plan references mirror objects but no mirror reader is configured')
                audio = mc.to_upload_audio(f.source_format, reader.read(f.ref), filename=f.original_name)
            pad_ok = audio.codec.startswith('pcm') or (audio.codec.startswith('opus') and opus_silence)
            if pad_ok:
                audio = mc.pad_with_silence(audio, f.lead_silence_s, f.trail_silence_s, opus_silence)
            last_audio = audio
        name = mc.upload_filename(DEVICE_TOKEN, audio, start)
        files.append((name, audio.body))
        audio_s += audio.duration_s
        lo, hi = min(lo, start), max(hi, start + audio.duration_s)
    return Materialized(files, audio_s, lo, hi)


# --------------------------------------------------------------------------
# Capture provenance seeding (fresh lane, device-bound)
# --------------------------------------------------------------------------


class CaptureSeeder(Protocol):
    def seed_user(self, uid: str) -> None: ...

    def seed_capture(
        self, uid: str, conversation_id: str, device_id: str, platform: str, started: float, finished: float
    ) -> None: ...


class StagingFirestoreSeeder:
    """Writes the server-capture conversation stub listen would have created.

    Runs only inside the staging runtime: the staging fence must pass and the
    process must be pointed at the ``staging`` database of ``based-hardware-dev``.
    """

    def __init__(self) -> None:
        if os.getenv('OMI_DEPLOYMENT') != 'staging' or os.getenv('FIRESTORE_DATABASE_ID') != 'staging':
            raise ReplayRefused('capture seeding requires OMI_DEPLOYMENT=staging and FIRESTORE_DATABASE_ID=staging')
        try:
            from utils.staging_fence import StagingFenceError, assert_staging_isolation  # lane 2, contract (i)
        except ImportError as exc:
            raise ReplayRefused('capture seeding requires utils.staging_fence (lane 2)') from exc
        try:
            assert_staging_isolation()
        except StagingFenceError as exc:
            # The message names variables and reason codes only, never values.
            raise ReplayRefused(str(exc)) from exc
        from database._client import get_firestore_client
        from database import conversations as conversations_db

        self.client = get_firestore_client()
        self.encode = conversations_db.encode_conversation_for_write
        self.seeded: set[str] = set()

    def seed_user(self, uid: str) -> None:
        if uid in self.seeded or not uid.startswith(pop.OWNER_PREFIX + '-'):
            return
        ref = self.client.collection('users').document(uid)
        ref.set(
            {
                'id': uid,
                'language': 'en',
                'private_cloud_sync_enabled': False,
                'data_protection_level': 'enhanced',
                'transcription_preferences': {'uses_custom_stt': False},
                'subscription': {'plan': 'basic', 'status': 'active'},
                'loadgen': True,
            },
            merge=True,
        )
        self.seeded.add(uid)

    def seed_capture(
        self, uid: str, conversation_id: str, device_id: str, platform: str, started: float, finished: float
    ) -> None:
        if not uid.startswith(pop.OWNER_PREFIX + '-'):
            raise ReplayRefused('seeding is limited to loadgen pseudo-owners')
        now = datetime.now(timezone.utc)
        capture = {
            'id': conversation_id,
            'created_at': now,
            'started_at': datetime.fromtimestamp(started, timezone.utc),
            'finished_at': datetime.fromtimestamp(finished, timezone.utc),
            'source': 'omi',
            'language': 'en',
            'structured': {
                'title': '',
                'overview': '',
                'emoji': '',
                'category': 'other',
                'action_items': [],
                'events': [],
            },
            'transcript_segments': [],
            'private_cloud_sync_enabled': False,
            'status': 'completed',
            'discarded': False,
            'is_locked': False,
            'data_protection_level': 'enhanced',
            'client_device_id': device_id,
            'client_platform': platform,
        }
        encoded = self.encode(uid, capture, level='enhanced')
        self.client.collection('users').document(uid).collection('conversations').document(conversation_id).set(encoded)


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------


@dataclass
class UploadResult:
    owner_id: str
    shape: str
    sequence: int
    lane_hint: str
    recording_key: str
    files: int
    audio_s: float
    scheduled_s: float
    sent_s: float = 0.0
    http_status: int = 0
    latency_ms: float = 0.0
    job_id: str = ''
    lane: str = ''
    conversation_id: str = ''
    seeded: bool = False
    skipped: bool = False  # a fresh upload not sent because its capture provenance could not be bound
    final_status: str = ''
    error: str = ''

    def row(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ReplayConfig:
    target: str
    admin_key: str
    time_scale: float = 1.0
    max_concurrency: int = 16
    poll: bool = False
    poll_interval_s: float = 15.0
    poll_timeout_s: float = 1800.0
    request_timeout_s: float = 120.0
    stop_after_s: float | None = None
    # Cloud Run invoker IAM: an ID token for the target, sent in X-Serverless-Authorization so the
    # app still sees the ADMIN_KEY Authorization header. None when the target admits all invokers (prod shape).
    id_token: Callable[[], str] | None = None


Sender = Callable[..., Awaitable[Any]]


@dataclass
class Replay:
    config: ReplayConfig
    plans: list[pop.PlannedUpload]
    reader: SourceReader | None = None
    seeder: CaptureSeeder | None = None
    opus_silence: bytes | None = None
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    results: list[UploadResult] = field(default_factory=list)

    def _auth(self, owner_id: str) -> dict[str, str]:
        headers = {'Authorization': f'Bearer {self.config.admin_key}{owner_id}'}
        if self.config.id_token is not None:
            headers['X-Serverless-Authorization'] = f'Bearer {self.config.id_token()}'
        return headers

    def _headers(self, upload: pop.PlannedUpload) -> dict[str, str]:
        return {
            **self._auth(upload.owner_id),
            'X-App-Platform': upload.platform,
            'X-Device-Id-Hash': upload.device_hash,
            'X-App-Version': 'loadgen',
            'X-Request-ID': f'loadgen-{uuid.uuid4().hex}',
        }

    async def _send_one(self, client: Any, upload: pop.PlannedUpload, started: float) -> UploadResult:
        result = UploadResult(
            upload.owner_id,
            upload.shape,
            upload.sequence,
            upload.lane_hint,
            upload.recording_key,
            len(upload.files),
            0.0,
            upload.at_s,
        )
        send_epoch = self.clock()
        result.sent_s = round(send_epoch - started, 3)
        try:
            m = materialize(upload, send_epoch, self.reader, opus_silence=self.opus_silence)
        except Exception as exc:  # a bad source must not stop the run
            result.error = f'materialize:{type(exc).__name__}'
            return result
        result.audio_s = round(m.audio_s, 3)
        headers = self._headers(upload)
        params: dict[str, str] = {}
        if self.seeder is not None and upload.lane_hint == 'fresh':
            # Without a bound manifest the server admits this as untrusted backfill (still 202), which
            # would shift the planned mix onto the backfill queue. Skip it and count it instead.
            conversation_id = f'lg-cap-{uuid.uuid4().hex}'
            device_id = build_client_device_id(upload.platform, upload.device_hash)
            if device_id is None:
                result.error, result.skipped = 'device_hash_invalid', True
                return result
            try:
                await asyncio.to_thread(self.seeder.seed_user, upload.owner_id)
                await asyncio.to_thread(
                    self.seeder.seed_capture,
                    upload.owner_id,
                    conversation_id,
                    device_id,
                    upload.platform,
                    m.capture_lo,
                    m.capture_hi,
                )
                manifest = await client.post(
                    f'{self.config.target}/v2/sync-capture-manifest',
                    json={
                        'conversation_id': conversation_id,
                        'files': [{'name': n, 'sha256': hashlib.sha256(b).hexdigest()} for n, b in m.files],
                    },
                    headers=headers,
                    timeout=self.config.request_timeout_s,
                )
                if manifest.status_code == 200:
                    headers['X-Omi-Sync-Capture-Manifest'] = manifest.json()['manifest']
                    params['conversation_id'] = conversation_id
                    result.conversation_id = conversation_id
                    result.seeded = True
                else:
                    result.error, result.skipped = f'manifest_http_{manifest.status_code}', True
                    return result
            except ReplayRefused:
                raise
            except Exception as exc:
                result.error, result.skipped = f'seed:{type(exc).__name__}', True
                return result
        t0 = time.monotonic()
        try:
            response = await client.post(
                f'{self.config.target}/v2/sync-local-files',
                params=params,
                files=[('files', (n, b, 'application/octet-stream')) for n, b in m.files],
                headers=headers,
                timeout=self.config.request_timeout_s,
            )
        except Exception as exc:
            result.error = f'upload:{type(exc).__name__}'
            return result
        result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.http_status = response.status_code
        if response.status_code == 202:
            body = response.json()
            result.job_id = str(body.get('job_id', ''))
            result.lane = str(body.get('lane', ''))
        else:
            result.error = result.error or f'upload_http_{response.status_code}'
        return result

    async def _poll(self, client: Any, result: UploadResult) -> None:
        deadline = time.monotonic() + self.config.poll_timeout_s
        headers = self._auth(result.owner_id)
        while time.monotonic() < deadline:
            await self.sleep(self.config.poll_interval_s)
            try:
                response = await client.get(
                    f'{self.config.target}/v2/sync-local-files/{result.job_id}', headers=headers, timeout=30
                )
            except Exception:
                continue
            if response.status_code != 200:
                continue
            status = str(response.json().get('status', ''))
            result.final_status = status
            if status in TERMINAL_STATUSES:
                return
        result.final_status = result.final_status or 'poll_timeout'

    async def run(self, client: Any) -> list[UploadResult]:
        started = self.clock()
        gate = asyncio.Semaphore(self.config.max_concurrency)
        by_owner: dict[str, list[pop.PlannedUpload]] = {}
        for plan in self.plans:
            by_owner.setdefault(plan.owner_id, []).append(plan)
        pollers: list[asyncio.Task[None]] = []

        async def owner_loop(uploads: list[pop.PlannedUpload]) -> None:
            for upload in sorted(uploads, key=lambda u: u.sequence):
                due = started + upload.at_s / self.config.time_scale
                if (
                    self.config.stop_after_s is not None
                    and upload.at_s / self.config.time_scale > self.config.stop_after_s
                ):
                    return
                delay = due - self.clock()
                if delay > 0:
                    await self.sleep(delay)
                async with gate:  # an app uploads serially; the gate bounds the fleet
                    result = await self._send_one(client, upload, started)
                self.results.append(result)
                if self.config.poll and result.job_id:
                    pollers.append(asyncio.create_task(self._poll(client, result)))

        await asyncio.gather(*(owner_loop(u) for u in by_owner.values()))
        if pollers:
            await asyncio.gather(*pollers)
        return self.results


def summarize_results(results: list[UploadResult]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_lane: dict[str, int] = {}
    by_final: dict[str, int] = {}
    latencies = sorted(r.latency_ms for r in results if r.http_status)
    for r in results:
        by_status[str(r.http_status or r.error)] = by_status.get(str(r.http_status or r.error), 0) + 1
        if r.lane:
            by_lane[r.lane] = by_lane.get(r.lane, 0) + 1
        if r.final_status:
            by_final[r.final_status] = by_final.get(r.final_status, 0) + 1

    def pct(q: float) -> float:
        return latencies[min(len(latencies) - 1, int(q * len(latencies)))] if latencies else 0.0

    accepted = [r for r in results if r.http_status == 202]
    span = max((r.sent_s for r in results), default=0.0)
    mismatch = sum(1 for r in accepted if r.lane and r.lane != r.lane_hint)
    skipped = sum(1 for r in results if r.skipped)
    # Fail closed: a run whose admitted lanes differ from the plan measured a different mix.
    failed_checks = [
        name
        for name, failed in (
            ('no_upload_accepted', not accepted),
            ('lane_hint_mismatch', mismatch > 0),
            ('fresh_skipped', skipped > 0),
        )
        if failed
    ]
    return {
        'uploads': len(results),
        'accepted': len(accepted),
        'owners': len({r.owner_id for r in results}),
        'audio_hours_accepted': round(sum(r.audio_s for r in accepted) / 3600, 3),
        'by_http_status': dict(sorted(by_status.items())),
        'by_lane': dict(sorted(by_lane.items())),
        'by_final_status': dict(sorted(by_final.items())),
        'seeded_fresh': sum(1 for r in results if r.seeded),
        'upload_latency_ms': {'p50': pct(0.5), 'p95': pct(0.95), 'max': latencies[-1] if latencies else 0.0},
        'achieved_uploads_per_min': round(len(results) / (span / 60), 3) if span > 0 else 0.0,
        'lane_hint_mismatch': mismatch,
        'fresh_skipped': skipped,
        'failed_checks': failed_checks,
    }


def population_record(results: list[UploadResult], header: dict[str, Any]) -> dict[str, Any]:
    """Lane 5 input: which pseudo-owner did what, with job and conversation ids (no audio)."""
    owners: dict[str, dict[str, Any]] = {}
    for r in sorted(results, key=lambda r: (r.owner_id, r.sequence)):
        o = owners.setdefault(r.owner_id, {'shape': r.shape, 'uploads': []})
        o['uploads'].append(
            {
                'sequence': r.sequence,
                'recording_key': r.recording_key,
                'job_id': r.job_id,
                'conversation_id': r.conversation_id,
                'lane': r.lane,
                'http_status': r.http_status,
                'final_status': r.final_status,
                'audio_s': r.audio_s,
            }
        )
    return {'run': header.get('spec', {}).get('run_id'), 'spec': header.get('spec'), 'owners': owners}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _load_manifest(path: str, *, storage_client: Any = None) -> dict[str, Any]:
    if path.startswith('gs://'):
        bucket, _, name = path[5:].partition('/')
        return json.loads(storage_client.bucket(bucket).blob(name).download_as_bytes())
    return json.loads(Path(path).read_text())


def cmd_plan(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile))
    if args.manifest:
        recordings = pop.recordings_from_manifest(_load_manifest(args.manifest, storage_client=_storage_client(args)))
    else:
        recordings = pop.synthetic_recordings(args.synthetic, file_seconds=args.synthetic_file_seconds)
    if args.burst_owners:
        spec = pop.burst_spec(
            args.run_id, args.burst_owners, recordings_per_owner=args.burst_recordings, seed=args.seed
        )
    else:
        spec = pop.PopulationSpec(
            run_id=args.run_id,
            owners=args.owners,
            duration_s=args.hours * 3600,
            rate_per_min=args.rate_per_min,
            percent_of_prod=args.percent_of_prod,
            seed=args.seed,
            start_utc_hour=args.start_utc_hour,
        )
    plans = pop.generate(recordings, profile, spec)
    pop.write_plan(args.out, plans, spec)
    print(json.dumps(pop.summarize(plans), indent=2, sort_keys=True))
    return 0


def _storage_client(args: argparse.Namespace) -> Any:
    from google.cloud import storage

    return storage.Client(project=getattr(args, 'mirror_project', None) or 'based-hardware-dev')


STAGING_SECRET_RE = re.compile(r'^projects/based-hardware-dev/secrets/staging-[a-z0-9-]+/versions/(latest|[0-9]+)$')


def read_staging_secret(resource: str, session: Any = None) -> str:
    """A ``staging-*`` Secret Manager value through ambient credentials (Workload Identity in-cluster)."""
    import base64

    if not STAGING_SECRET_RE.match(resource):
        raise ReplayRefused('secrets must be based-hardware-dev staging-* resources')
    if session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(creds)
    response = session.get(f'https://secretmanager.googleapis.com/v1/{resource}:access', timeout=30)
    if response.status_code != 200:
        raise ReplayRefused(f'cannot read {resource.split("/")[3]} (HTTP {response.status_code})')
    return base64.b64decode(response.json()['payload']['data']).decode()


def _secret(args: argparse.Namespace, env_name: str, resource: str | None) -> str:
    return read_staging_secret(resource) if resource else os.environ.get(env_name, '')


class CachedIdToken:
    """Google ID token for one audience, refreshed before its one-hour expiry."""

    def __init__(self, audience: str, fetch: Callable[[str], str] | None = None, ttl_s: float = 3000.0):
        self.audience = audience
        self.ttl_s = ttl_s
        self._fetch = fetch
        self._token = ''
        self._at = 0.0

    def __call__(self) -> str:
        if not self._token or time.monotonic() - self._at > self.ttl_s:
            if self._fetch is None:
                from google.auth.transport.requests import Request
                from google.oauth2 import id_token

                self._fetch = lambda aud: id_token.fetch_id_token(Request(), aud)
            self._token = self._fetch(self.audience)
            self._at = time.monotonic()
        return self._token


async def _run_async(args: argparse.Namespace) -> int:
    import httpx

    target = check_target(args.target, allow_local=args.allow_local)
    where = check_load_host(target)
    admin_key = _secret(args, args.admin_key_env, args.admin_key_secret)
    if len(admin_key) < 16:
        raise ReplayRefused('the staging ADMIN_KEY is missing (--admin-key-secret or --admin-key-env)')
    header, plans = pop.read_plan(args.plan)
    check_plan_lanes(plans, seed_capture=args.seed_capture, unseeded_fresh=args.unseeded_fresh)
    reader = None
    if any(f.ref.startswith('mirror:') for p in plans for f in p.files):
        secret = _secret(args, args.mirror_key_env, args.mirror_key_secret)
        if not secret:
            raise ReplayRefused('the staging mirror secret is missing (--mirror-key-secret or --mirror-key-env)')
        if args.mirror_bucket != 'based-hardware-dev-staging-mirror' and not args.allow_local:
            raise ReplayRefused('mirror bucket must be based-hardware-dev-staging-mirror')
        reader = MirrorReader(_storage_client(args).bucket(args.mirror_bucket), mc.derive_mirror_key(secret))
    seeder = StagingFirestoreSeeder() if args.seed_capture else None
    config = ReplayConfig(
        id_token=CachedIdToken(target) if args.cloud_run_id_token else None,
        target=target,
        admin_key=admin_key,
        time_scale=args.time_scale,
        max_concurrency=args.max_concurrency,
        poll=args.poll,
        poll_timeout_s=args.poll_timeout_s,
        stop_after_s=args.stop_after_s,
    )
    replay = Replay(config, plans, reader=reader, seeder=seeder, opus_silence=mc.encoded_opus_silence_packet())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(json.dumps({'event': 'replay_start', 'where': where, 'uploads': len(plans), 'run': header['spec']['run_id']}))
    limits = httpx.Limits(max_connections=args.max_concurrency * 2, max_keepalive_connections=args.max_concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        results = await replay.run(client)
    with open(out / 'results.jsonl', 'w', encoding='utf-8') as handle:
        for r in results:
            handle.write(json.dumps(r.row(), sort_keys=True) + '\n')
    summary = summarize_results(results)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    (out / 'population.json').write_text(json.dumps(population_record(results, header), indent=2, sort_keys=True))
    print(json.dumps({'event': 'replay_done', **summary}, sort_keys=True))
    return 1 if summary['failed_checks'] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Staging population replay (swarm lane 4)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('plan', help='generate a population plan (pure; no network unless --manifest gs://)')
    p.add_argument('--run-id', required=True)
    p.add_argument('--profile', default=str(PROFILE_PATH))
    p.add_argument('--manifest', help='mirror manifest (local path or gs://based-hardware-dev-staging-mirror/...)')
    p.add_argument('--synthetic', type=int, default=200, help='synthetic recordings when no manifest')
    p.add_argument('--synthetic-file-seconds', type=float, default=60.0)
    p.add_argument('--owners', type=int, default=50)
    p.add_argument('--hours', type=float, default=2.0)
    p.add_argument('--percent-of-prod', type=float, default=1.0)
    p.add_argument('--rate-per-min', type=float)
    p.add_argument('--start-utc-hour', type=int)
    p.add_argument('--burst-owners', type=int, default=0, help='N-owner burst mode at full per-owner intensity')
    p.add_argument('--burst-recordings', type=int, default=12)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--mirror-project', default='based-hardware-dev')
    p.add_argument('--out', required=True)
    p.set_defaults(func=cmd_plan)

    r = sub.add_parser('run', help='send a plan to staging (m1-mac-studio or in-cluster only)')
    r.add_argument('--plan', required=True)
    r.add_argument('--target', required=True)
    r.add_argument('--out', required=True)
    r.add_argument('--admin-key-env', default='STAGING_ADMIN_KEY')
    r.add_argument('--admin-key-secret', help='projects/based-hardware-dev/secrets/staging-admin-key/versions/latest')
    r.add_argument('--mirror-key-env', default='STAGING_ENCRYPTION_SECRET')
    r.add_argument(
        '--mirror-key-secret', help='projects/based-hardware-dev/secrets/staging-encryption-secret/versions/latest'
    )
    r.add_argument('--cloud-run-id-token', action='store_true', help='send X-Serverless-Authorization (invoker IAM on)')
    r.add_argument('--mirror-bucket', default='based-hardware-dev-staging-mirror')
    r.add_argument('--mirror-project', default='based-hardware-dev')
    r.add_argument('--seed-capture', action='store_true', help='device-bound fresh uploads (in-cluster, fence)')
    r.add_argument(
        '--unseeded-fresh',
        action='store_true',
        help='send fresh uploads without seeding (only when the target admits legacy fresh); mismatches still fail',
    )
    r.add_argument('--time-scale', type=float, default=1.0)
    r.add_argument('--max-concurrency', type=int, default=16)
    r.add_argument('--poll', action='store_true')
    r.add_argument('--poll-timeout-s', type=float, default=1800.0)
    r.add_argument('--stop-after-s', type=float)
    r.add_argument('--allow-local', action='store_true', help='hermetic stack on localhost only')
    r.set_defaults(func=lambda a: asyncio.run(_run_async(a)))

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ReplayRefused as exc:
        print(json.dumps({'event': 'replay_refused', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
