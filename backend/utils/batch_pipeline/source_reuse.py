"""Exact sync-file identity. No clocks, text, or custody claims prove reuse.

Only ordinary, anonymous sync input participates. File boundaries and canonical
sample ranges are stable across bundle membership. Unknown clocks, coverage
trimming, alternate decoders and explicit/native targets keep their old path.
"""

from dataclasses import replace
import hashlib
import hmac
import json
import os

from prometheus_client import Counter

from utils.sync.capture_clock import is_early_capture_time, is_implausible_future_capture_time
from utils.sync.clock_run import capture_clock_run_from_path
from utils.sync.content_id import compute_sync_segment_id
from utils.sync.files import get_timestamp_from_path

EVENTS = Counter('omi_batch_pipeline_source_reuse_total', 'Observed exact-source reuse decisions', ['event'])
SECONDS = Counter(
    'omi_batch_pipeline_source_reuse_seconds_total', 'Observed source input seconds, not GPU wall time', ['event']
)


def enabled():
    # Default on; malformed explicit values close new equivalence decisions.
    return os.getenv('BATCH_SOURCE_REUSE_ENABLED', 'true').strip().lower() in {'true', '1', 'on', 'yes'}


def observe(event: str, seconds: float = 0.0) -> None:
    if event not in {
        'reused',
        'avoided_asr_input',
        'alias_wait',
        'alias_refusal',
        'uncovered_tail',
        'duplicate_projection_refusal',
        'custody_failure',
    }:
        raise ValueError('closed source reuse event required')
    EVENTS.labels(event).inc()
    if seconds > 0:
        SECONDS.labels(event).inc(seconds)


def eligible(paths, context):
    if not enabled() or not context or not context.get('client_device_id') or not 1 <= len(paths) <= 64:
        return False
    if (
        context.get('source_reuse_excluded')
        or context.get('capture_evidence_claims')
        or context.get('recording_session_id')
    ):
        return False  # Existing source-frame/custody rules remain authoritative.
    return all(
        not is_early_capture_time(get_timestamp_from_path(path))
        and not is_implausible_future_capture_time(get_timestamp_from_path(path))
        and not capture_clock_run_from_path(path)
        for path in paths
    )


def decode_sources(paths, *, uid, context, decoder, max_seconds, received_at=None):
    """Hash original bytes before the destructive WAL decoder; never dedupe PCM alone."""
    # Include source semantics, device and explicit epoch metadata, where present.
    scope = json.dumps(
        {name: context.get(name) for name in ('client_device_id', 'source', 'should_lock', 'clock_epoch')},
        sort_keys=True,
        separators=(',', ':'),
    )
    sources = sorted(
        [(path, compute_sync_segment_id(uid, path)) for path in paths],
        key=lambda value: (get_timestamp_from_path(value[0]), os.path.basename(value[0]), value[1]),
    )
    seen = set()
    for path, original in sources:
        if original in seen:
            continue  # The same original file inside this upload is one source.
        seen.add(original)
        for unit in decoder([path], max_seconds=max_seconds, **({'received_at': received_at} if received_at else {})):
            # A changed split boundary or decoder output abstains from equivalence.
            payload = json.dumps(
                [
                    'sync-file-v1',
                    scope,
                    original,
                    unit.capture_at,
                    unit.duration_seconds,
                    hashlib.sha256(unit.wav).hexdigest(),
                ],
                separators=(',', ':'),
            )
            secret = os.getenv('SYNC_CONTENT_ID_SECRET') or os.getenv('ENCRYPTION_SECRET')
            if not secret:
                raise RuntimeError('source identity secret required')
            key = hmac.new(secret.encode(), f'{uid}\n{payload}'.encode(), hashlib.sha256).hexdigest()
            yield replace(unit, source_reuse_key=key)
