"""Who gets per-window speaker evidence: a manifest dispute abstains windows, not the recording.

Batch-authoritative conversations always qualify, so this follows the batch ramp
with no separate step. Beta apps qualify through the episodes client marker, which
only means TestFlight while episodes admit the beta channel alone. The wider
SPEAKER_EVIDENCE_MODE cohort also qualifies. Reads fail closed.
"""

from config.batch_conversation_speakers import has_batch_authority
from config.episodes import episodes_client_channels
from config.refactor_modes import default_on, serving_for
from utils.episodes.client_gate import client_seen_cached

SPEAKER_PER_WINDOW_ENV = 'SPEAKER_PER_WINDOW_ENABLED'
_BETA_ONLY = frozenset({'beta'})


def per_window_evidence(uid, segments) -> bool:
    if serving_for('SPEAKER_EVIDENCE_MODE', uid):
        return True
    if not default_on(SPEAKER_PER_WINDOW_ENV):
        return False
    if has_batch_authority(segments):
        return True
    return episodes_client_channels() == _BETA_ONLY and client_seen_cached(uid)
