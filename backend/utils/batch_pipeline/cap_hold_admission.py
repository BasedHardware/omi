"""Cap-held audio re-enters through batch admission, not legacy transcription (contract (h); C11).

``cap_hold_recovery.recover_selected`` (driven by ``/v2/cap-hold-recovery/sweep``) calls
``admit_held`` under its row claim once legacy sync is draining or dark. The held source is decoded
to one WAV and admitted like an upload under a content id derived from the hold, so a retried sweep
finds its own batch ledger and never creates a second unit. Batch projection then owns the
conversation and usage; the hold row is handed off, never settled as legacy-transcribed.

Paid exactly once: a hold that legacy recovery already started spending on (any piece receipt or
processed path) is not eligible; it finishes on the legacy path during ``draining``.

This module imports nothing from ``utils.sync.pipeline`` (C11 keeps the neutral helpers elsewhere).
"""

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from typing import Any, Literal, Mapping

from utils.batch_pipeline.audio import RATE, audio_unit
from utils.batch_pipeline.capture_decode import UNIT_FRAMES, canonical_pcm
from utils.sync.legacy_dark import LegacySyncMode

logger = logging.getLogger(__name__)

HeldOutcome = Literal['admitted', 'already_admitted', 'covered', 'privacy_blocked', 'retry']
# Sealing/staging live sources are not immutable yet; the recovery worker returns early for them too.
_UNSEALED = frozenset({'staging', 'sealing'})
# Terminal or legacy-owned states: never (re-)admitted.
_DONE = frozenset({'batch_admitted', 'completed', 'retained', 'purged'})


@dataclass(frozen=True)
class HeldAdmission:
    outcome: HeldOutcome
    batch_job_id: str | None = None


def held_content_id(uid: str, hold_id: str) -> str:
    """Derived content id; never the legacy ledger row the hold already owns."""
    return hashlib.sha256(f'cap_hold_v1\0{uid}\0{hold_id}'.encode()).hexdigest()


def eligible(row: Mapping[str, Any]) -> bool:
    """No legacy spend has started on this hold and its source is sealed."""
    return (
        not row.get('piece_receipts')
        and not row.get('processed_paths')
        and row.get('state') not in _UNSEALED
        and row.get('state') not in _DONE
    )


def enabled_for(row: Mapping[str, Any], mode: LegacySyncMode | None = None) -> bool:
    """cap_hold_mode == 'batch_hold' (contract (c)) while legacy is draining or dark."""
    if mode is None:
        from utils.sync import legacy_dark

        mode = legacy_dark.current_mode()
    return mode is not LegacySyncMode.ON and eligible(row)


def wav_units(path: str, capture_at: float, max_seconds: float):
    """One held WAV as bounded capture units, on the capture clock (as ``decode_units`` packs WAL)."""
    unit_frames = min(UNIT_FRAMES, int(max_seconds * RATE))
    if unit_frames < 1 or max_seconds > 7200:
        raise ValueError('invalid dedicated capture-unit ceiling')
    pcm = canonical_pcm(path)
    if not pcm:
        raise ValueError('empty held audio')
    step = unit_frames * 2
    for offset in range(0, len(pcm), step):
        yield audio_unit(capture_at + offset / (2 * RATE), pcm[offset : offset + step])


async def admit_held(uid: str, snapshot: Any, row: Mapping[str, Any]) -> HeldAdmission:
    """Admit one claimed hold into batch. The caller holds the hold-row lease."""
    from utils.batch_pipeline import intake
    from utils.executors import run_blocking, storage_executor
    from utils.sync import cap_hold
    from utils import funded_processing
    from utils.batch_pipeline.held_coverage import HeldDecoder

    if not eligible(row):
        raise ValueError('hold already has legacy spend or an unsealed source')
    hold_id = snapshot.id
    content_id = held_content_id(uid, hold_id)
    meta = await run_blocking(storage_executor, cap_hold.metadata, uid, dict(row))
    directory = await run_blocking(storage_executor, cap_hold.recovery_directory, uid)
    try:
        path = str(Path(directory.name) / 'held.wav')
        await run_blocking(storage_executor, cap_hold.read_audio, uid, dict(row), path)
        capture_at = float(meta['timestamp'])
        decoder = HeldDecoder(uid, path, capture_at, meta, legacy=wav_units)
        response = await intake.accept_upload(
            uid=uid,
            job_id=content_id[:32],
            content_id=content_id,
            paths=[path],
            lane='backfill',
            recording_age_seconds=None,
            source=meta['source'],
            # The owner's processing choice funded this audio; it is not re-locked.
            should_lock=False,
            conversation_id=meta.get('target_conversation_id'),
            client_device_id=meta.get('client_device_id'),
            client_platform=meta.get('client_platform'),
            intake_context={'origin': 'cap_hold', 'recording_session_id': meta.get('recording_session_id')},
            decode=decoder,
            usage_period=funded_processing.period_id(),
        )
    finally:
        await run_blocking(storage_executor, directory.cleanup)
    if decoder.all_covered and response is not None and response.status_code == 200:
        return HeldAdmission('covered')
    job_id = intake.JOB_PREFIX + content_id[:32]
    code = _code(response)
    if response is not None and response.status_code == 202:
        return HeldAdmission('admitted', job_id)
    if code == 'sync_content_in_progress' and _body(response).get('job_id') == job_id:
        # Our own derived content, admitted by an earlier sweep whose status read was ambiguous.
        return HeldAdmission('already_admitted', job_id)
    if code == 'sync_batch_privacy_blocked':
        return HeldAdmission('privacy_blocked')
    try:
        logger.warning('event=cap_hold_admission outcome=retry code=%s', code or 'none')
    except Exception:
        pass
    return HeldAdmission('retry')


def _body(response: Any) -> dict:
    import json

    try:
        body = json.loads(response.body)
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _code(response: Any) -> str | None:
    if response is None:
        return None
    code = _body(response).get('code')
    return code if isinstance(code, str) and len(code) <= 64 else None
