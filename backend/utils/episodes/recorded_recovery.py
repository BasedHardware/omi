"""Route a capped capture's evidence once to each recorded-time episode window."""

from dataclasses import replace
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from database import episode_receipts
from config.episode_attach import walk_context_enabled, optimizations_enabled
from utils.episodes import policy, recovery
from utils.episodes.moment import MomentInput


class RecoveryReceipts:
    """One walk's receipts, bound to its owner's CAS revision.

    Refresh after another writer changes the owner; advance only after our own
    successful CAS. Failed notes never add speculative consumption.
    """

    def __init__(self, uid, conversation_id, collaborators, owner=None):
        self.uid, self.conversation_id = uid, conversation_id
        self.client = collaborators.firestore_client
        self.episode_id = (owner or {}).get('id')
        self.version = (owner or {}).get('state_version')
        self.loaded = False
        self.owner = owner
        self.row: Any = None

    def invalidate(self):
        self.owner = None
        self.row = None
        self.loaded = False

    def read(self, owner=None):
        if owner is not None and (owner.get('id'), owner.get('state_version')) != (self.episode_id, self.version):
            self.loaded = False
            self.episode_id, self.version = owner.get('id'), owner.get('state_version')
        if owner is not None:
            self.owner = owner
        if not self.loaded:
            self.legacy, self.exists = episode_receipts.get_consumed_ids(
                self.uid, self.conversation_id, all_shards=True, firestore_client=self.client
            )
            # Content can exist independently (placed live speech writes only
            # content proof), so an absent legacy base cannot skip this read.
            self.content, _ = episode_receipts.get_consumed_ids(
                self.uid,
                recovery.receipt_namespace(self.conversation_id),
                all_shards=True,
                firestore_client=self.client,
            )
            self.loaded = True
        return set(self.legacy), self.exists, set(self.content)

    def committed(self, owner, receipts):
        self.owner = owner
        self.episode_id, self.version = owner['id'], owner['state_version']
        self.legacy.update(receipts.get(self.conversation_id) or [])
        self.content.update(receipts.get(recovery.receipt_namespace(self.conversation_id)) or [])
        if self.conversation_id in receipts:
            self.exists = True


def read_receipts(uid, moment, c, episode, consumption_owner):
    """Read both namespaces once, preserving legacy adoption and revision checks."""
    recovered = moment.trigger == 'sync_recovery'
    receipt_state = moment.recovery_receipts if recovered and optimizations_enabled() else None
    if receipt_state is not None:
        consumed, receipts_exist, consumed_content = receipt_state.read(episode)
    else:
        consumed, receipts_exist = episode_receipts.get_consumed_ids(
            uid,
            moment.conversation_id,
            # The finalization tail replays the whole stored transcript: only the
            # archives hold ids old enough to matter there. Live batches are recent.
            all_shards=moment.trigger == 'finalize' or recovered,
            firestore_client=c.firestore_client,
        )
        consumed_content, _ = (
            episode_receipts.get_consumed_ids(
                uid,
                recovery.receipt_namespace(moment.conversation_id),
                all_shards=True,
                firestore_client=c.firestore_client,
            )
            if recovered
            else (set(), False)
        )
    if not receipts_exist:
        # Pre-receipts episodes kept consumption in their document; adopt it into
        # the receipts on this write so the finalization tail still dedupes.
        consumed |= set(((consumption_owner or {}).get('applied_segment_ids') or {}).get(moment.conversation_id) or [])
    return consumed, receipts_exist, consumed_content


def unconsumed_moments(
    uid: str, conversation_id: str, moments: Iterable[MomentInput], collaborators: Any, *, receipts=None
) -> Iterator[MomentInput]:
    """Read the receipts once for the whole walk: a long capture replays hundreds of finished batches,
    and each would otherwise re-read the episode and every receipt shard just to skip itself."""
    if not optimizations_enabled():
        yield from moments
        return
    try:
        receipts = receipts or RecoveryReceipts(uid, conversation_id, collaborators)
        legacy, _, content = receipts.read()
    except Exception:
        yield from moments
        return
    for moment in moments:
        if recovery.select_segments(moment.segments, legacy, content, -1.0, recovered=True)[0]:
            yield replace(moment, recovery_receipts=receipts)


def record_walk(
    uid: str, episode_id: str, walk: Iterable[MomentInput], collaborators: Any, record_moment: Callable
) -> str:
    outcome = 'skipped_applied'
    for moment in walk:
        outcome = record_moment(uid, moment, collaborators, member_episode_id=episode_id)
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome


def record_windows(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    collaborators: Any,
    record_moment: Callable,
    *,
    now,
) -> str:
    origin = policy.utc(row.get('started_at'))
    if origin is None:
        return 'no_episode'
    if not windows:
        return 'no_episode'
    # Membership is singular. Retain the whole conversation's evidence in its
    # owner, including speech beyond the owner's visible four-hour window.
    owner = windows[0]
    outcome = 'skipped_applied'
    walk = recovery.moments(conversation_id, row, now=now, calendar_identity=row.get('calendar_identity'))
    receipts = RecoveryReceipts(uid, conversation_id, collaborators, owner) if collaborators is not None else None
    if receipts is not None and walk_context_enabled():
        receipts.row = row
    for moment in unconsumed_moments(uid, conversation_id, walk, collaborators, receipts=receipts):
        moment = replace(moment, ended_at=min(moment.ended_at, owner['last_activity_at']))
        outcome = record_moment(uid, moment, collaborators, member_episode_id=str(owner['id']))
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome
