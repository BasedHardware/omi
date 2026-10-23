"""Runtime contract for folding a silence-split conversation into its predecessor.

Live capture ends a conversation after about two minutes without speech, so one
occasion (a dinner, a walk, a work session) can become several rows. After a
pendant conversation finishes, the durable finalizer may ask Jev whether it
continues the immediately preceding conversation from the same device
(``utils/conversations/smart_merge.py``).

The 2026-09-29 decision made ``merge`` the default; ``off`` is the kill
switch, ``shadow`` records decisions without merging, and any other non-empty
value fails to ``off``. The same-recording wall-clock rescue runs after a
legacy gap check skips a pair, and only when stored recording lineage proves
both fragments came from one live recording.

Pure module: stdlib only, flags read at the call boundary, never at import.
"""

from __future__ import annotations

import os

from config.refactor_switches import default_on as rollout_default_on
from enum import Enum

SMART_MERGE_MODE_ENV = 'CONVERSATION_SMART_MERGE_MODE'
SMART_MERGE_AUDIT_ENV = 'CONVERSATION_SMART_MERGE_AUDIT_ENABLED'
SMART_MERGE_FLATTEN_ENV = 'CONVERSATION_SMART_MERGE_FLATTEN_ENABLED'
SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV = 'CONVERSATION_SMART_MERGE_FLATTEN_CHAIN_REPAIR'
_ON = frozenset({'true', 'on', '1', 'yes'})


class SmartMergeMode(str, Enum):
    OFF = 'off'  # byte-identical to no feature
    SHADOW = 'shadow'  # decide and record, never merge
    MERGE = 'merge'  # decide, record, and fold the conversation into its predecessor


DEFAULT_SMART_MERGE_MODE = SmartMergeMode.MERGE


def smart_merge_mode() -> SmartMergeMode:
    """Unset or blank is the default (``merge``); an unrecognized value is ``off``.

    The asymmetry is deliberate: the variable is the kill switch, so a mistyped
    ``of`` or ``disabled`` must stop the feature, not silently keep it running.
    """
    raw = os.getenv(SMART_MERGE_MODE_ENV, '').strip().lower()
    if not raw:
        return DEFAULT_SMART_MERGE_MODE
    try:
        return SmartMergeMode(raw)
    except ValueError:
        return SmartMergeMode.OFF


def smart_merge_audit_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off.

    Off restores the pre-audit absorb exactly (no gate read, no audit write). A
    typo in the kill switch therefore turns the audit off, never the merge.
    """
    raw = os.getenv(SMART_MERGE_AUDIT_ENV, '').strip().lower()
    return rollout_default_on(SMART_MERGE_AUDIT_ENV, not raw or raw in _ON)


def smart_merge_flatten_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off.

    Off restores the pre-flatten absorb exactly: a donor carrying sync bridge
    ancestry is ineligible again, no ancestor is read or re-pointed, and the
    survivor/donor payloads keep their old shape. A typo therefore disables
    flattening, never the merge. A committed flatten still finishes cleanup
    after the flag is turned off: completing queued work is not new permission.
    """
    raw = os.getenv(SMART_MERGE_FLATTEN_ENV, '').strip().lower()
    return rollout_default_on(SMART_MERGE_FLATTEN_ENV, not raw or raw in _ON)


def smart_merge_flatten_chain_repair_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off.

    Ordinary sync absorbs re-point only the rows they match, so a canonical's
    cumulative ``sync_merged_from`` can hold ancestors that still redirect to an
    intermediate hop inside that same lineage. On, the flatten accepts such a
    chain and re-points every hop at the survivor; off restores the strict
    one-hop check, which rejects the whole absorb.
    """
    raw = os.getenv(SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, '').strip().lower()
    return rollout_default_on(SMART_MERGE_FLATTEN_CHAIN_REPAIR_ENV, not raw or raw in _ON)


# Sources the benchmark measured. Pendant pairs were 113 of 138; desktop recall
# was 0 of 2 and desktop rows carry meeting receipts and on-device projections.
ELIGIBLE_SOURCES = frozenset({'omi'})

# Merge when Jev's P(same occasion) is at least this cutoff (dev threshold: the
# smallest cutoff with zero dev false merges, plus a 0.025 margin).
MERGE_THRESHOLD = 0.35

# Ask only inside this gap window. The minimum is the live split itself
# (``models/conversation_continuity.DEFAULT_GAP_SECONDS``); both the recorded gap
# and the speech gap must reach it, which also skips sync shards whose start
# drifted. Above one hour only 2 of 9 pairs were continuations.
MIN_GAP_SECONDS = 120
MAX_GAP_SECONDS = 60 * 60

# Both sides need this many transcript words; the benchmark sampled only such
# pairs, and near-empty fragments were its main missed-merge class.
MIN_WORDS = 25

# The benchmark's call budget: a slower answer keeps the conversations separate.
JEV_TIMEOUT_SECONDS = 3.0
JEV_MAX_ATTEMPTS = 1

# Chain-aware state (benchmark input variant iv). A stretch links conversations
# whose recorded gap is strictly under STRETCH_LINK_SECONDS.
MAX_STRETCH_FRAGMENTS = 4
STRETCH_LINK_SECONDS = 30 * 60
STRETCH_SUMMARY_CHARS = 400
TRANSCRIPT_EXCERPT_CHARS = 2_500
# A fragment is A (full summary) in the next decision, so the ledger keeps more than the stretch shows.
LEDGER_OVERVIEW_CHARS = 4_000
LEDGER_TITLE_CHARS = 300

# Snowball guards. The benchmark scored pairs, not merged spans; it suggested a
# 3-4 h cap without measuring one, so this takes the conservative end.
MAX_MERGED_SPAN_SECONDS = 3 * 60 * 60
MAX_MERGED_SEGMENTS = 4_000
MAX_FRAGMENTS = 12

# Rows fetched to find the predecessor and its stretch context.
PRECEDING_QUERY_LIMIT = 6

# A survivor refresh lease outlives one slow reprocess, never a crashed worker for long.
REFRESH_LEASE_SECONDS = 10 * 60

QUESTION_VERSION = 'adjacent_merge_a_iv1'
