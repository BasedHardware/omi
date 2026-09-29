"""Runtime contract for folding a silence-split conversation into its predecessor.

Live capture ends a conversation after about two minutes without speech, so one
occasion (a dinner, a walk, a work session) can become several rows. After a
pendant conversation finishes, the durable finalizer may ask Jev whether it
continues the immediately preceding conversation from the same device
(``utils/conversations/smart_merge.py``).

Every number below comes from the 2026-09-29 offline benchmark on the owner's
pendant history (138 labelled adjacent pairs, labels frozen before scoring;
the report is private and not in the repository). Held-out results for the
selected configuration: AUC 0.918, 25 of 49 continuations merged, 0 of 19
separate occasions merged (exact one-sided 95% upper bound on the false-merge
rate: 14.6%). The verdict was *shadow first*: unattended merging needs at
least 100 reviewed live negatives with at most one false merge. The score is
badly calibrated (true continuations average 0.3-0.4) and the nearest held-out
negative scored 0.305, so the threshold is a cutoff, not a probability, and
any wording, state-format or model change needs a re-measure.

Pure module: stdlib only, flags read at the call boundary, never at import.
"""

from __future__ import annotations

import os
from enum import Enum

SMART_MERGE_MODE_ENV = 'CONVERSATION_SMART_MERGE_MODE'
SMART_MERGE_UID_ALLOWLIST_ENV = 'CONVERSATION_SMART_MERGE_UID_ALLOWLIST'


class SmartMergeMode(str, Enum):
    OFF = 'off'  # byte-identical to no feature
    SHADOW = 'shadow'  # decide and record, never merge
    MERGE = 'merge'  # decide, record, and fold the conversation into its predecessor


def smart_merge_mode() -> SmartMergeMode:
    """Unknown or empty values are ``off``: a typo must never enable merging."""
    raw = os.getenv(SMART_MERGE_MODE_ENV, '').strip().lower()
    try:
        return SmartMergeMode(raw)
    except ValueError:
        return SmartMergeMode.OFF


def smart_merge_uid_allowed(uid: str) -> bool:
    """An empty allowlist admits every user; a non-empty one admits only its members."""
    allowlist = {item.strip() for item in os.getenv(SMART_MERGE_UID_ALLOWLIST_ENV, '').split(',') if item.strip()}
    return not allowlist or uid in allowlist


# Sources the benchmark measured. Pendant pairs were 113 of 138; desktop recall
# was 0 of 2 and desktop rows carry meeting receipts and on-device projections.
ELIGIBLE_SOURCES = frozenset({'omi'})

# Merge when Jev's P(same occasion) is at least this cutoff (dev threshold: the
# smallest cutoff with zero dev false merges, plus a 0.025 margin).
MERGE_THRESHOLD = 0.35

# Ask only inside this gap window. The minimum is the live split itself
# (``utils/conversation_continuity.DEFAULT_GAP_SECONDS``); both the recorded gap
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
