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
stored line's nonempty ``sync:`` scope; anything ambiguous is kept.

The same switch gates safe strict-overlap deferral in
``utils/sync/recording_lineage.py`` (``ambiguous_pending`` instead of guessing
among overlapping generations, then the existing retryable failed-segment path)
and the bounded lineage diagnostics it added (stage counts, ``id_probe`` reads
and the ``event=sync_lineage_stamp_append`` telemetry line).

``SYNC_LINEAGE_LIVE_DEDUPE_ENABLED`` unset or blank means on. Only an explicit
on-token keeps it on when set; every other value — including a mistyped kill
switch — means off, and off restores the exact previous intake path: identical
persistence, results and enrichment decisions, main-format lineage logging, no
probe reads, and no dedupe stats or markers.

The switch alone does not widen the change: activation additionally requires
``sync_lineage_resolve_active_for(uid)``, so it reaches only users admitted to
lineage binding.

Pure module: stdlib plus the sibling lineage gate, read at the call boundary,
never at import.
"""

from __future__ import annotations

import os

from config.sync_lineage import sync_lineage_resolve_active_for

SYNC_LINEAGE_LIVE_DEDUPE_ENV = 'SYNC_LINEAGE_LIVE_DEDUPE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def sync_live_dedupe_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES


def sync_live_dedupe_active_for(uid: object) -> bool:
    """The intake gate: this switch on and the uid admitted to lineage binding."""
    return sync_live_dedupe_enabled() and sync_lineage_resolve_active_for(uid)
