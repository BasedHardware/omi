"""Process-local evidence custody counters, initialized before Backend's first scrape."""

import os

from prometheus_client import Counter

_REVISION = os.environ.get('K_REVISION') or 'unknown'
_FENCE = Counter('omi_speaker_evidence_fence_total', 'Terminal evidence transaction outcomes.', ['revision', 'outcome'])
COMMITTED_MARKER_ABSENT = _FENCE.labels(_REVISION, 'committed_marker_absent')
COMMITTED_MARKER_PRESENT = _FENCE.labels(_REVISION, 'committed_marker_present')
REFUSED_MARKER_PRESENT = _FENCE.labels(_REVISION, 'refused_marker_present')
WRITER_FAILED = _FENCE.labels(_REVISION, 'failed')

_ERASURE = Counter(
    'omi_speaker_evidence_erasure_total', 'Post-root evidence sweep attempts and outcomes.', ['revision', 'outcome']
)
SWEEP_STARTED = _ERASURE.labels(_REVISION, 'started')
SWEEP_CHECKED = _ERASURE.labels(_REVISION, 'checked')
SWEEP_FAILED = _ERASURE.labels(_REVISION, 'failed')
SWEEP_DISABLED = _ERASURE.labels(_REVISION, 'disabled')

REMAINING = Counter(
    'omi_speaker_evidence_remaining_total', 'Evidence child references observed after a sweep.', ['revision']
).labels(_REVISION)
