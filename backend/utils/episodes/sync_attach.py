"""Sync attachment orchestration; database transactions remain authoritative."""

import random
import time
from typing import Any, Mapping

from config.episode_attach import owner_reuse_enabled, row_visibility_enabled
from config.recorded_time import recorded_episodes_enabled
from database import episodes as episodes_db, episode_attach_memo
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.conversations.recorded_time import conversation_span
from utils.episodes import capture_groups as episode_groups
from utils.episodes import late_member
from utils.episodes.visibility import hidden_conversation, hidden_member

SYNC_UPDATE = 'sync_update'


def attach(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    c: Any,
    *,
    absorbed_from=None,
    attach_once,
    attach_recorded,
    repoint_absorbed,
    repoint_donors,
    end_discarded,
    record_recovered,
) -> str:
    hidden = (
        hidden_member(dict(row))
        if row_visibility_enabled()
        else hidden_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    )
    if is_relevance_discarded(row) or hidden:
        end_discarded(uid, conversation_id, row, SYNC_UPDATE, c)
        return 'skipped_discarded'
    if canonical := episode_groups.canonical_row(uid, conversation_id, row, firestore_client=c.firestore_client):
        primary = str(canonical.get('id') or episode_groups.primary_id(row))
        owner = episodes_db.get_episode_for_conversation(uid, primary, firestore_client=c.firestore_client)
        if owner and primary in (owner.get('recovered_conversation_ids') or []):
            episode_groups.join_duplicates(uid, owner, primary, canonical, firestore_client=c.firestore_client)
            return 'attached'
        return attach(
            uid,
            primary,
            canonical,
            c,
            attach_once=attach_once,
            attach_recorded=attach_recorded,
            repoint_absorbed=repoint_absorbed,
            repoint_donors=repoint_donors,
            end_discarded=end_discarded,
            record_recovered=record_recovered,
        )
    if (
        recorded_episodes_enabled()
        and not absorbed_from
        and episode_attach_memo.matches(uid, conversation_id, row, firestore_client=c.firestore_client)
    ):
        return 'attached_unchanged'
    # Re-read both membership and the boundary on every lost CAS. A last WAL
    # append cannot rely on another append arriving to repair a lost attachment.
    for attempt in range(3):
        try:
            if absorbed_from:
                donor = episodes_db.get_episode_for_conversation(
                    uid, absorbed_from, firestore_client=c.firestore_client
                )
                if donor and absorbed_from in (donor.get('conversation_ids') or []):
                    repoint_absorbed(uid, donor, absorbed_from, conversation_id, c)
            repoint_donors(uid, conversation_id, row, c)
            owner = (
                None
                if recorded_episodes_enabled()
                else episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
            )
            try:
                if recorded_episodes_enabled() and owner_reuse_enabled() and (span := conversation_span(row)):
                    owner = attach_recorded(uid, conversation_id, row, span.recorded_start, span.recorded_end, c)
                    outcome = 'recorded'
                else:
                    outcome = (
                        attach_once(uid, conversation_id, row, c)
                        if recorded_episodes_enabled() or not owner
                        else 'attached'
                    )
                    owner = episodes_db.get_episode_for_conversation(
                        uid, conversation_id, firestore_client=c.firestore_client
                    )
            except episodes_db.EpisodeConflict as error:
                if str(error) != 'conversation_hidden':
                    raise
                # Member admission read current visibility inside the transaction.
                # A stale visible caller still owes discard cleanup, not retries.
                # Repointed recovery owners use a different conflict reason.
                end_discarded(uid, conversation_id, row, SYNC_UPDATE, c)
                return 'skipped_discarded'
            if owner is not None:
                if conversation_id not in (owner.get('recovered_conversation_ids') or []):
                    recovered_ids = [*(owner.get('recovered_conversation_ids') or []), conversation_id]
                    owner = episodes_db.update_episode(
                        uid,
                        str(owner['id']),
                        expected_version=int(owner.get('state_version') or 0),
                        updates={'recovered_conversation_ids': list(dict.fromkeys(recovered_ids))},
                        firestore_client=c.firestore_client,
                    )
                joined = episode_groups.join_duplicates(
                    uid, owner, conversation_id, row, firestore_client=c.firestore_client
                )
                owner = joined or owner
                recovered = (
                    record_recovered(uid, str(owner['id']), conversation_id, row, c, owner=owner)
                    if owner_reuse_enabled()
                    else record_recovered(uid, str(owner['id']), conversation_id, row, c)
                )
                if recovered == 'skipped_discarded':
                    end_discarded(uid, conversation_id, row, SYNC_UPDATE, c)
                    return recovered
                if recovered in {'applied', 'skipped_applied'} and not absorbed_from:
                    episode_attach_memo.complete(uid, conversation_id, row, owner, firestore_client=c.firestore_client)
            late_member.joined(uid, conversation_id, row, owner, c)
            return outcome
        except episodes_db.EpisodeConflict:
            if attempt == 2:
                return 'conflict'
            time.sleep(random.uniform(0.01, 0.05) * (attempt + 1))
    return 'conflict'
