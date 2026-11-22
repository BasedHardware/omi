"""Runtime contract for dropping safety-WAL segments that repeat live speech.

A WAL is uploaded whole whenever any frame missed the socket, so a segment bound
to a live generation (``utils/sync/recording_lineage.py``) can re-upload speech
the socket already transcribed, reworded by a second STT pass. When this switch
is on, ``utils/sync/live_speech_dedupe.py`` drops an incoming segment only when
``utils/sync/capture_repeat_evidence.py`` independently proves its full
source-frame coverage (a unique ``sync_vad`` receipt whose touched frames the
live row's ``origin=live`` snapshot positively covers) AND a bounded live
window lexically covers it; lexical or exact-range text alone never
suppresses — an unproven identical utterance is legitimate repetition. The
exact-retry pass then drops identical normalized text plus identical absolute
range or segment id only for a capture-proven segment or one sharing the
stored line's nonempty ``sync:`` scope; anything ambiguous is kept. On admitted
live targets this contract composes with fleet safety-WAL fuzzy dedupe: the
lineage lexical and exact-retry passes run first, then the unchanged fleet
matcher runs on their survivors. Final survivors determine append and repeat
timing. This contract retains precedence over capture-refactor serving
proposals, which may not drop a lexical abstention.
Non-cohort users retain their existing fleet/refactor policy.

Finalized batch-live targets also apply the stored-donor lexical rule to late
sync appends, including older uploads without source-frame receipts. This
chooses the already durable record transcript only when the bounded lexical
matcher independently covers the incoming words, including protected negations
and numbers; time overlap alone never removes speech.

Stored sync donors consolidated into a live target use the same gate at the
transactional content-transfer boundary, including smart absorb. Committed
frame coverage also requires lexical safety checks; without it, the bounded lexical
matcher supplies independent repeat proof, followed by the same exact-retry
pass. Original donor receipts and the frozen pre-merge live snapshot stay
separate. Stored chapters can contain up to 4096 segments; above the fresh
64-segment budget their lexical search uses a 90-second neighborhood to avoid
abstaining on a crowded 30-minute candidate pool. Over-budget content is kept.
Retained timing overlap is observation only. See
``utils/sync/ARCHITECTURE.md`` for bridge fields and widening gates.

The same switch gates safe strict-overlap deferral in
``utils/sync/recording_lineage.py`` (``ambiguous_pending`` instead of guessing
among overlapping generations, then the existing retryable failed-segment path)
and the bounded lineage diagnostics it added (stage counts, ``id_probe`` reads
and the ``event=sync_lineage_stamp_append`` telemetry line).

``SYNC_LINEAGE_LIVE_DEDUPE_ENABLED`` unset or blank means on. Only an explicit
on-token keeps it on when set; every other value — including a mistyped kill
switch — means off, and off restores the exact previous intake path: identical
persistence, results and enrichment decisions, main-format lineage logging and
no probe reads. Append timing on the fleet path remains independently observable.

The switch alone does not widen the write-side change: activation additionally requires
``sync_lineage_resolve_active_for(uid)``, so it reaches only users admitted to
lineage binding. Prompt rendering independently uses the same kill switch
for a non-mutating multi-scope batch projection. It prefers placed copies,
requires bounded lexical coverage or identical text at the same endpoints,
and preserves manual/translated lines and uncertain repetition. No stored
transcript, annotation, audio receipt or paid-work admission is changed.

Pure module: stdlib plus the sibling lineage gate, read at the call boundary,
never at import.
"""

from __future__ import annotations

import os

from config.refactor_switches import default_on as rollout_default_on

from config.sync_lineage import sync_lineage_resolve_active_for

SYNC_LINEAGE_LIVE_DEDUPE_ENV = 'SYNC_LINEAGE_LIVE_DEDUPE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_live_dedupe_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, '').strip().lower()
    return rollout_default_on(SYNC_LINEAGE_LIVE_DEDUPE_ENV, not raw or raw in _ON_VALUES)


def sync_live_dedupe_active_for(uid: object) -> bool:
    """The intake gate: this switch on and the uid admitted to lineage binding."""
    return sync_live_dedupe_enabled() and sync_lineage_resolve_active_for(uid)
