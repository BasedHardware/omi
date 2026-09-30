"""Deterministic rules for folding a conversation into its predecessor.

Everything here is pure: it reads decoded conversation dicts (transcripts
already decrypted by the database adapter) and returns verdicts or write
payloads. The Firestore transaction in ``database/smart_merge.py`` calls
``absorb_payloads`` with rows it re-read inside the transaction, so every
precondition is checked against current data, not the caller's snapshot.

Partition, exclusions and gap arithmetic follow the sync bridge
(``utils/sync/assignment.compatible_capture`` / ``auto_mergeable`` and
``utils/conversation_continuity``) so the two merge paths agree on what a
device partition and a user-managed row are.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from config.conversation_smart_merge import (
    ELIGIBLE_SOURCES,
    LEDGER_OVERVIEW_CHARS,
    LEDGER_TITLE_CHARS,
    MAX_FRAGMENTS,
    MAX_GAP_SECONDS,
    MAX_MERGED_SEGMENTS,
    MAX_MERGED_SPAN_SECONDS,
    MAX_STRETCH_FRAGMENTS,
    MIN_GAP_SECONDS,
    MIN_WORDS,
    STRETCH_LINK_SECONDS,
)
from utils.conversations.smart_merge_state import Fragment
from utils.conversations.wake_word import find_wake_word_matches
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

SMART_MERGE_FIELD = 'smart_merge'
DECISION_FIELD = 'smart_merge_decision'
ROLE_SURVIVOR = 'survivor'
ROLE_DONOR = 'donor'

# Rows a person has curated, shared, or grouped keep their identity and content.
_USER_MANAGED_FLAGS = (
    'user_title',
    'starred',
    'folder_user_set',
    'sync_relevance_user_kept',
    'has_photos',
    'is_locked',
    'manual_speaker_assignments',
    'capture_group',
)


class SkipReason:
    """Bounded reasons a pair never reaches Jev (metric label values)."""

    UID_NOT_ALLOWED = 'uid_not_allowed'
    NOT_ELIGIBLE_SOURCE = 'not_eligible_source'
    NOT_CAPTURE_END = 'not_capture_end'
    CONVERSATION_NOT_ELIGIBLE = 'conversation_not_eligible'
    USER_MANAGED = 'user_managed'
    WAKE_WORD = 'wake_word'
    NO_PREDECESSOR = 'no_predecessor'
    PREDECESSOR_NOT_COMPLETED = 'predecessor_not_completed'
    PREDECESSOR_USER_ENDED = 'predecessor_user_ended'
    PREDECESSOR_REFRESH_PENDING = 'predecessor_refresh_pending'
    GAP_OUT_OF_WINDOW = 'gap_out_of_window'
    TOO_FEW_WORDS = 'too_few_words'
    SPAN_CAP = 'span_cap'
    SEGMENT_CAP = 'segment_cap'
    FRAGMENT_CAP = 'fragment_cap'
    REFRESH_UNAVAILABLE = 'refresh_unavailable'


def smart_merge_state(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get(SMART_MERGE_FIELD)
    return value if isinstance(value, Mapping) else {}


def is_donor(row: Mapping[str, Any]) -> bool:
    return smart_merge_state(row).get('role') == ROLE_DONOR


def revision(row: Mapping[str, Any]) -> int:
    return int(smart_merge_state(row).get('revision') or 0)


def refreshed_revision(row: Mapping[str, Any]) -> int:
    return int(smart_merge_state(row).get('refreshed_revision') or 0)


def refresh_owed(row: Mapping[str, Any]) -> bool:
    """A survivor whose transcript changed after its last completed refresh."""
    return refreshed_revision(row) < revision(row)


def partition(row: Mapping[str, Any]) -> tuple[Any, Any, bool]:
    """Unknown device is its own partition, never a wildcard (same rule as sync)."""
    return (row.get('source'), row.get('client_device_id'), bool(row.get('is_locked')))


def user_managed(row: Mapping[str, Any]) -> bool:
    if any(row.get(flag) for flag in _USER_MANAGED_FLAGS):
        return True
    if row.get('visibility', 'private') not in (None, 'private'):
        return True
    external = row.get('external_data')
    return isinstance(external, Mapping) and bool(external.get('duplicate_capture_of'))


def user_ended(row: Mapping[str, Any]) -> bool:
    """The user stopped this capture themselves: a split we honor."""
    decision = row.get('relevance_decision')
    return isinstance(decision, Mapping) and decision.get('trigger') == 'client_finalize'


def has_wake_word(segments: Sequence[Mapping[str, Any]]) -> bool:
    return bool(find_wake_word_matches(segments))


def word_count(segments: Iterable[Mapping[str, Any]]) -> int:
    return sum(len(str(segment.get('text') or '').split()) for segment in segments)


def _epoch(value: Any) -> Optional[float]:
    return value.timestamp() if isinstance(value, datetime) else None


def speech_bounds(row: Mapping[str, Any], segments: Sequence[Mapping[str, Any]]) -> Optional[tuple[float, float]]:
    """Absolute first-speech start and last-speech end, as sync assignment computes them."""
    origin = _epoch(row.get('started_at'))
    starts = [float(value) for value in (s.get('start') for s in segments) if isinstance(value, (int, float))]
    ends = [float(value) for value in (s.get('end') for s in segments) if isinstance(value, (int, float))]
    if origin is None or not starts or not ends:
        return None
    return origin + min(starts), origin + max(ends)


def fragment_of(row: Mapping[str, Any]) -> Optional[Fragment]:
    started, finished = row.get('started_at'), row.get('finished_at')
    if not isinstance(started, datetime) or not isinstance(finished, datetime) or not row.get('id'):
        return None
    stored = row.get('structured')
    structured: Mapping[str, Any] = stored if isinstance(stored, Mapping) else {}
    return Fragment(
        id=str(row['id']),
        started_at=started,
        finished_at=finished,
        title=str(structured.get('title') or '')[:LEDGER_TITLE_CHARS],
        overview=str(structured.get('overview') or '')[:LEDGER_OVERVIEW_CHARS],
    )


def ledger_fragments(row: Mapping[str, Any]) -> list[Fragment]:
    """The fragments a row represents: its ledger once it absorbed any, else itself."""
    entries = smart_merge_state(row).get('fragments')
    if isinstance(entries, list) and entries:
        fragments = [Fragment.from_ledger_entry(entry) for entry in entries if isinstance(entry, Mapping)]
        return sorted((f for f in fragments if f is not None), key=lambda f: f.started_at)
    own = fragment_of(row)
    return [own] if own is not None else []


def fragment_segments(
    row: Mapping[str, Any], segments: Sequence[Mapping[str, Any]], fragment: Fragment
) -> list[Mapping[str, Any]]:
    """The survivor's segments that belong to one fragment (by absolute start time)."""
    origin = _epoch(row.get('started_at'))
    if origin is None:
        return list(segments)
    floor = fragment.started_at.timestamp()
    return [s for s in segments if isinstance(s.get('start'), (int, float)) and origin + float(s['start']) >= floor]


def stretch_before(a: Fragment, candidates: Iterable[Fragment]) -> list[Fragment]:
    """Up to four fragments that chain into A with gaps under 30 minutes, oldest first."""
    earlier = sorted(
        {f.id: f for f in candidates if f.id != a.id and f.started_at < a.started_at}.values(),
        key=lambda f: f.started_at,
    )
    chain: list[Fragment] = []
    head = a
    for fragment in reversed(earlier):
        if (head.started_at - fragment.finished_at).total_seconds() >= STRETCH_LINK_SECONDS:
            break
        chain.insert(0, fragment)
        head = fragment
    return chain[-MAX_STRETCH_FRAGMENTS:]


def new_conversation_skip(
    row: Mapping[str, Any], segments: Sequence[Mapping[str, Any]], *, capture_end: bool
) -> Optional[str]:
    """Why the just-finished conversation cannot join anything, or ``None``."""
    if row.get('source') not in ELIGIBLE_SOURCES:
        return SkipReason.NOT_ELIGIBLE_SOURCE
    if not capture_end:
        return SkipReason.NOT_CAPTURE_END
    # A merge target never becomes a donor: its own donors would outlive it
    # (the deletion purge follows one level of ``sync_merged_from``).
    if (
        row.get('status') != 'completed'
        or row.get('deleted')
        or row.get('discarded')
        or smart_merge_state(row)
        or row.get('sync_merged_from')
        or not segments
    ):
        return SkipReason.CONVERSATION_NOT_ELIGIBLE
    if row.get('uses_custom_stt'):
        return SkipReason.REFRESH_UNAVAILABLE
    if user_managed(row):
        return SkipReason.USER_MANAGED
    if has_wake_word(segments):
        return SkipReason.WAKE_WORD
    return None


def predecessor_status_skip(row: Mapping[str, Any]) -> Optional[str]:
    """Checks that need only the projected metadata row."""
    if row.get('deleted') or row.get('discarded') or is_donor(row):
        return SkipReason.PREDECESSOR_NOT_COMPLETED
    if row.get('status') != 'completed':
        return SkipReason.PREDECESSOR_NOT_COMPLETED
    if row.get('uses_custom_stt'):
        return SkipReason.REFRESH_UNAVAILABLE
    if user_managed(row):
        return SkipReason.USER_MANAGED
    if user_ended(row):
        return SkipReason.PREDECESSOR_USER_ENDED
    return None


@dataclass(frozen=True)
class PairCheck:
    reason: Optional[str]  # None when Jev may be asked
    gap_seconds: Optional[float] = None
    speech_gap_seconds: Optional[float] = None


def check_pair(
    survivor: Mapping[str, Any],
    survivor_segments: Sequence[Mapping[str, Any]],
    new: Mapping[str, Any],
    new_segments: Sequence[Mapping[str, Any]],
) -> PairCheck:
    """Full deterministic gate for (survivor, new), both decoded and current."""
    reason = predecessor_status_skip(survivor)
    if reason is not None:
        return PairCheck(reason)
    if partition(survivor) != partition(new):
        return PairCheck(SkipReason.NO_PREDECESSOR)
    if refresh_owed(survivor):
        return PairCheck(SkipReason.PREDECESSOR_REFRESH_PENDING)
    if has_wake_word(survivor_segments):
        return PairCheck(SkipReason.WAKE_WORD)
    survivor_speech = speech_bounds(survivor, survivor_segments)
    new_speech = speech_bounds(new, new_segments)
    survivor_end, new_start = survivor.get('finished_at'), new.get('started_at')
    if survivor_speech is None or new_speech is None or not isinstance(survivor_end, datetime):
        return PairCheck(SkipReason.GAP_OUT_OF_WINDOW)
    if not isinstance(new_start, datetime):
        return PairCheck(SkipReason.GAP_OUT_OF_WINDOW)
    gap = (new_start - survivor_end).total_seconds()
    speech_gap = new_speech[0] - survivor_speech[1]
    check = PairCheck(None, gap, speech_gap)
    if not MIN_GAP_SECONDS <= gap <= MAX_GAP_SECONDS or speech_gap < MIN_GAP_SECONDS:
        return PairCheck(SkipReason.GAP_OUT_OF_WINDOW, gap, speech_gap)
    fragments = ledger_fragments(survivor)
    last = fragments[-1] if fragments else None
    a_segments = fragment_segments(survivor, survivor_segments, last) if last else survivor_segments
    if word_count(a_segments) < MIN_WORDS or word_count(new_segments) < MIN_WORDS:
        return PairCheck(SkipReason.TOO_FEW_WORDS, gap, speech_gap)
    if new_speech[1] - survivor_speech[0] > MAX_MERGED_SPAN_SECONDS:
        return PairCheck(SkipReason.SPAN_CAP, gap, speech_gap)
    if len(survivor_segments) + len(new_segments) > MAX_MERGED_SEGMENTS:
        return PairCheck(SkipReason.SEGMENT_CAP, gap, speech_gap)
    if len(fragments) + 1 > MAX_FRAGMENTS:
        return PairCheck(SkipReason.FRAGMENT_CAP, gap, speech_gap)
    return check


def _stronger_protection(*levels: Optional[str]) -> str:
    # Missing means the default, which is enhanced (database/helpers.py).
    return 'enhanced' if any((level or 'enhanced') == 'enhanced' for level in levels) else 'standard'


def rebase_donor_segments(
    survivor: Mapping[str, Any],
    survivor_segments: Sequence[Mapping[str, Any]],
    donor: Mapping[str, Any],
    donor_segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Survivor transcript followed by the donor's, on the survivor's absolute timeline.

    Conversation-local speaker numbers are reallocated so a donor voice can
    never collapse into a different survivor voice with the same number; the
    refresh's speaker resolution may later unify genuinely equal voices.
    Segment ids are kept, so an undo can remove exactly the donor's segments.
    """
    offset = donor['started_at'].timestamp() - survivor['started_at'].timestamp()
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(survivor_segments)
    merged = [dict(segment) for segment in deepcopy(list(survivor_segments))]
    for segment in (dict(item) for item in deepcopy(list(donor_segments))):
        if not segment.get('speaker_id_scope'):
            segment['speaker_id_scope'] = f"legacy-conversation:{donor['id']}:{segment.get('speaker_id')}"
        allocator.assign(segment)
        segment['start'] = float(segment.get('start') or 0.0) + offset
        segment['end'] = float(segment.get('end') or 0.0) + offset
        merged.append(segment)
    merged.sort(key=lambda segment: float(segment.get('start') or 0.0))
    return merged


def absorb_payloads(
    survivor: Mapping[str, Any],
    survivor_segments: Sequence[Mapping[str, Any]],
    donor: Mapping[str, Any],
    donor_segments: Sequence[Mapping[str, Any]],
    *,
    merged_at: datetime,
    decision: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decoded survivor update and donor tombstone update for one absorb."""
    fragments = ledger_fragments(survivor)
    donor_fragment = fragment_of(donor)
    if donor_fragment is not None:
        fragments.append(donor_fragment)
    next_revision = revision(survivor) + 1
    state = dict(smart_merge_state(survivor))
    state.update(
        {
            'role': ROLE_SURVIVOR,
            'revision': next_revision,
            'refreshed_revision': refreshed_revision(survivor),
            'fragments': [fragment.as_ledger_entry() for fragment in fragments],
        }
    )
    state.pop('refresh_lease', None)
    survivor_update: dict[str, Any] = {
        'transcript_segments': rebase_donor_segments(survivor, survivor_segments, donor, donor_segments),
        'finished_at': max(survivor['finished_at'], donor['finished_at']),
        'has_content': True,
        'private_cloud_sync_enabled': bool(
            survivor.get('private_cloud_sync_enabled') or donor.get('private_cloud_sync_enabled')
        ),
        'data_protection_level': _stronger_protection(
            survivor.get('data_protection_level'), donor.get('data_protection_level')
        ),
        'sync_merged_from': sorted({*(survivor.get('sync_merged_from') or []), str(donor['id'])}),
        SMART_MERGE_FIELD: state,
    }
    # The processor's existing transcript fence is sync_content_revision. Stamp
    # live survivors too: a processor started before this absorb must not write
    # its old transcript or summary over the newly joined occasion.
    survivor_update['sync_content_revision'] = int(survivor.get('sync_content_revision') or 0) + 1
    donor_update: dict[str, Any] = {
        'deleted': True,
        # Hide the redirect from discarded == False list indexes, exactly like a
        # sync bridge donor; include_discarded readers drop it via is_soft_deleted.
        'discarded': True,
        'sync_merged_into': str(survivor['id']),
        'sync_content_revision': int(donor.get('sync_content_revision') or 0) + 1,
        SMART_MERGE_FIELD: {
            'role': ROLE_DONOR,
            'survivor_id': str(survivor['id']),
            'survivor_revision': next_revision,
            'merged_at': merged_at,
        },
        DECISION_FIELD: dict(decision),
    }
    return survivor_update, donor_update
