"""Session-local merge proofs; separate from Firestore payloads and retry receipts."""

from typing import Dict, List

from config.audio_timeline import live_capture_window_merge_union_enabled
from models.capture_window_proof import CaptureWindowProof
from models.transcript_segment import TranscriptSegment

CaptureMergeTails = Dict[str, Dict[str, CaptureWindowProof]]


def snapshot_proofs(
    tails: CaptureMergeTails, conversation_id: str, fresh: List[TranscriptSegment]
) -> Dict[str, Dict[str, CaptureWindowProof]]:
    if not live_capture_window_merge_union_enabled():
        return {}
    proofs = dict(tails.get(conversation_id, {}))
    proofs.update({str(s.id): s.capture_merge_proof for s in fresh if s.capture_merge_proof is not None})
    return {'live_capture_proofs': proofs}


def acknowledge_proofs(tails: CaptureMergeTails, conversation_id: str, proofs: Dict[str, CaptureWindowProof]) -> None:
    if not live_capture_window_merge_union_enabled():
        tails.clear()
        return
    tails.pop(conversation_id, None)
    tails[conversation_id] = proofs
    # Fixed-size proofs for only the mutable tail of 32 recent conversations.
    # No translator, audio or unbounded send history survives the callback.
    while len(tails) > 32:
        tails.pop(next(iter(tails)))
