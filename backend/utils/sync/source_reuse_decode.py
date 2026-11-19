"""CPU-only exact-file proof packing; never imported by source receipt readers."""

from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any
import hashlib
import hmac
import json
import os

from utils.batch_pipeline import source_reuse
from utils.batch_pipeline.audio import AudioUnit
from utils.sync.capture_clock import is_early_capture_time, is_implausible_future_capture_time
from utils.sync.clock_run import capture_clock_run_from_path
from utils.sync.content_id import compute_sync_segment_id
from utils.sync.files import get_timestamp_from_path


def decode_for_intake(
    paths: Sequence[str],
    max_seconds: float,
    uid: str,
    context: Mapping[str, Any] | None,
    *,
    decoder: Callable[..., Iterable[AudioUnit]],
) -> Generator[AudioUnit, None, None]:
    """Opt in at the source-reuse caller; leave the shared clock/coverage path intact."""
    if context and eligible(paths, context):
        yield from decode_sources(
            paths,
            uid=uid,
            context=context,
            decoder=decoder,
            max_seconds=max_seconds,
            received_at=context.get('capture_received_at'),
        )
        return
    from utils.capture.batch_coverage import decode_for_intake as decode_coverage

    yield from decode_coverage(paths, max_seconds, uid, context, decoder=decoder)


def eligible(paths: Sequence[str], context: Mapping[str, Any] | None) -> bool:
    if not source_reuse.enabled() or not context or not context.get('client_device_id') or not 1 <= len(paths) <= 64:
        return False
    if (
        context.get('source_reuse_excluded')
        or context.get('capture_evidence_claims')
        or context.get('recording_session_id')
        or context.get('capture_clock_policy')
    ):
        return False  # Existing source-frame/custody rules remain authoritative.
    try:
        return all(
            not is_early_capture_time(get_timestamp_from_path(path))
            and not is_implausible_future_capture_time(get_timestamp_from_path(path))
            and not capture_clock_run_from_path(path)
            for path in paths
        )
    except ValueError:
        # Filename clock metadata is only an optional reuse proof. An adapter
        # may decode a different naming scheme; it retains admission authority.
        return False


def decode_sources(
    paths: Sequence[str],
    *,
    uid: str,
    context: Mapping[str, Any],
    decoder: Callable[..., Iterable[AudioUnit]],
    max_seconds: float,
    received_at: float | None = None,
) -> Generator[AudioUnit, None, None]:
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
            # The file HMAC is a private, owner-bound derived key. Do not
            # reread process secrets in batch stages or hash bare PCM globally.
            key = hmac.new(bytes.fromhex(original), f'{uid}\n{payload}'.encode(), hashlib.sha256).hexdigest()
            yield replace(unit, source_reuse_key=key)
