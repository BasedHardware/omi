"""Live re-derive reads and undo for the per-owner v3 repair tool (utils/conversations/v3/backfill.py).

One owner's finished live v3 windows in [since, until) are replanned from their source recordings by
the live planner after a planner fix. Only rows nobody else owns are offered as open priors; every
other row the loaded sources touch is offered as a published finished row, so its speech, claims and
audio stay exactly where they are, and it is never written. The projection commit itself stays in
database/conversations_v3.py (commit_projection's ``retire``). Runbook: docs/runbooks/conversations-v3.md.
"""

import json
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import conversations_v3 as store
from database import conversations_v3_leases as leases
from database.transcript_pointer import TranscriptBlobAbsent, TranscriptShredded
from utils.conversations.v3 import Conflict, policy

# Documents (sources and rows) one partition's started_at read may return; more blocks the partition.
REDERIVE_LIVE_LIMIT = 256
# Fields whose presence means the owner acted on a row (or another conversation absorbed it).
OWNER_EDIT_FIELDS = (
    'user_title',
    'user_overview',
    'user_corrections',
    'has_transcript_corrections',
    'transcript_correction_overlay',
    'manual_speaker_assignments',
    'starred',
    'folder_user_set',
    'photos',
    'has_photos',
    'sync_relevance_user_kept',
    'v3_claims_transferred_to',
)


def live_row_protection(raw, *, since, until):
    """Why a live v3 row must stay exactly as it is during a re-derive (None: it may be rebuilt)."""
    if raw.get('deleted') or raw.get('sync_merged_into'):
        return 'deleted'
    if raw.get('status') == 'in_progress':
        return 'open'
    started, finished = raw.get('started_at'), raw.get('finished_at')
    if not started or not finished or started < since or finished > until:
        return 'boundary'
    if raw.get('backfilled') and not raw.get('v3_rederive_live_run'):
        return 'backfilled'
    if raw.get('is_locked'):
        return 'locked'
    if raw.get('data_protection_level') == 'private':
        return 'private'
    visibility = raw.get('visibility')
    if visibility not in (None, 'private'):
        return 'shared'
    if any(raw.get(field) for field in OWNER_EDIT_FIELDS):
        return 'edited'
    if raw.get('discarded'):
        return 'discarded'
    if (
        raw.get('v3_process_pending')
        or raw.get('v3_backfill_process_pending')
        or raw.get('tile_state') == 'transcribing'
        or raw.get('status') not in ('completed', 'processing', 'failed')
    ):
        return 'notes_pending'
    return None


def live_source_block(raw):
    """Why a source recording must not be replanned now (None: it is sealed and settled)."""
    if raw.get('deleted') or raw.get('sync_merged_into'):
        return 'deleted'
    if raw.get('data_protection_level') == 'private':
        return 'private'
    if raw.get('v3_backfill_run'):
        return 'backfill_donor'
    if raw.get('v3_pending') or raw.get('status') != 'completed' or policy.transcription_pending(raw):
        return 'unsealed'
    if policy.transcription_failed(raw):
        return 'transcription_failed'
    if raw.get('v3_audio_purge_pending'):
        return 'purge_pending'
    return None


def _rederive_live_prior(row, raw):
    """A live row offered to the planner as an open window that keeps its id (legacy re-derive's reset).

    Its sources are recomputed from the lines it receives, and the stored document is kept verbatim
    (``_v3_raw``) for the undo ledger and for the unchanged-window check.
    """
    return {
        **store._rederive_prior(row),  # pyright: ignore[reportPrivateUsage] -- the reviewed re-derive reset
        'v3_recording_ids': [],
        '_v3_original': row,
        '_v3_raw': raw,
    }


def load_live_rederive(uid, *, since, until, run_id, firestore_client=None):
    """One live re-derive partition: sealed sources, their rows and every row their claims name.

    Returns (recordings, existing, cache, counts). ``existing`` holds eligible rows as open priors
    and protected rows (``_v3_protected``: reason) as finished published rows; ``counts`` is the
    ledger's skipped/blocked tally. Overflow blocks the partition, never a partial replan.
    """
    client = firestore_client or store.get_firestore_client()
    if store.account_deletion_blocks_user_work(uid, firestore_client=client):
        raise Conflict('account_deletion')
    coll = store.user_conversations(client, uid)
    snapshots = list(
        coll.where(filter=FieldFilter('started_at', '>=', since))
        .where(filter=FieldFilter('started_at', '<', until))
        .order_by('started_at')
        .limit(REDERIVE_LIVE_LIMIT + 1)
        .stream()
    )
    if len(snapshots) > REDERIVE_LIVE_LIMIT:
        raise Conflict('backfill_partition_budget')
    counts = {'rows_eligible': 0, 'visible_before': 0}

    def count(name):
        counts[name] = counts.get(name, 0) + 1

    raws, sources, rows = {}, {}, {}
    for snapshot in snapshots:
        raw = snapshot.to_dict() or {}
        raws[snapshot.id] = raw
        if raw.get('v3_derived') and not raw.get('recording'):
            rows[snapshot.id] = snapshot
        elif raw.get('recording') and not raw.get('v3_derived'):
            sources[snapshot.id] = snapshot

    def read(ids):
        ordered = sorted(ids)
        found = {}
        for start in range(0, len(ordered), store.CLAIM_READ_CHUNK):
            for snapshot in client.get_all(
                [coll.document(cid) for cid in ordered[start : start + store.CLAIM_READ_CHUNK]]
            ):
                if snapshot.exists:
                    found[snapshot.id] = snapshot
        return found

    # Sources every in-window row names, then every row any loaded source's claims name.
    def named_sources(raw):
        ids = set(raw.get('v3_recording_ids') or [])
        ids.update(p.get('recording_id') for p in raw.get('recording_pieces') or [] if p.get('recording_id'))
        return ids

    wanted = set().union(*(named_sources(raws[cid]) for cid in rows)) - sources.keys() if rows else set()
    if len(sources) + len(wanted) > store.SOURCE_LIMIT:
        raise Conflict('v3_source_closure_budget')
    for cid, snapshot in read(wanted).items():
        raw = snapshot.to_dict() or {}
        if raw.get('recording') and not raw.get('v3_derived'):
            raws[cid], sources[cid] = raw, snapshot
    claimed = {
        c.get('conversation_id')
        for rid in sources
        for c in raws[rid].get('claims') or []
        if isinstance(c, dict) and isinstance(c.get('conversation_id'), str)
    } - rows.keys()
    if len(rows) + len(claimed) > store.DERIVED_LIMIT:
        raise Conflict('v3_derived_budget')
    for cid, snapshot in read(claimed).items():
        raw = snapshot.to_dict() or {}
        if raw.get('v3_derived') and not raw.get('recording'):
            raws[cid], rows[cid] = raw, snapshot

    # Sources: sealed and readable ones are replanned; the rest are left out with their rows.
    recordings, blocked = {}, set()
    for rid, snapshot in sources.items():
        reason = live_source_block(raws[rid])
        row = None if reason else store.recording_input(uid, snapshot)
        if not reason and (row is None or row.get('_v3_unreadable')):
            reason = 'unreadable'
        if reason or row is None:
            blocked.add(rid)
            count('sources_blocked_' + (reason or 'unreadable'))
            continue
        if raws[rid].get('deleted_spans'):
            count('sources_with_deleted_spans')
        recordings[rid] = {**row, '_v3_rederive_live': True}
    # An open window's sources belong to the live builder until it closes.
    for cid in rows:
        if raws[cid].get('status') == 'in_progress':
            for rid in named_sources(raws[cid]) & recordings.keys():
                recordings.pop(rid)
                blocked.add(rid)
                count('sources_blocked_open_window')

    existing = {}
    for cid, snapshot in rows.items():
        raw = raws[cid]
        reason = live_row_protection(raw, since=since, until=until)
        if reason == 'deleted':
            count('skipped_deleted')
            continue
        if reason is None and named_sources(raw) & blocked:
            reason = 'source_blocked'
        if reason is None and not (named_sources(raw) and named_sources(raw) <= recordings.keys()):
            # Speech a row cannot be rebuilt from stays in that row.
            reason = 'source_missing'
        try:
            row = store.decode_row(uid, snapshot)
        except (ValueError, TypeError, FileNotFoundError, TranscriptBlobAbsent, TranscriptShredded, Conflict):
            row = None
        if row is None:
            # Undecodable: kept as it is, and its claims still fence the replan.
            row = {**raw, 'id': cid, 'transcript_segments': [], '_v3_revision': snapshot.update_time}
            reason = reason or 'unreadable'
        if reason:
            count('protected_' + reason)
            # Offered as a published finished row: its lines, claims and audio stay with it.
            existing[cid] = {
                **row,
                'status': 'completed' if row.get('status') == 'in_progress' else row.get('status'),
                '_v3_protected': reason,
            }
        else:
            count('rows_eligible')
            if not row.get('home_hidden'):
                count('visible_before')
            existing[cid] = _rederive_live_prior(row, raw)
    state = leases.lease_ref(client, uid, store.BACKFILL_LEASE).get().to_dict() or {}
    cache = json.loads(store.decrypt(state['outline_cache'], uid)) if state.get('outline_cache') else []
    return recordings, existing, cache, counts


def live_undo_blocker(uid, run_id, ids, *, firestore_client=None):
    """Checked before any group restores, so a refusal leaves the run whole (each group re-checks)."""
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    deleted = client.collection('users').document(uid).collection('deleted_conversations')
    for cid in ids:
        if deleted.document(cid).get().exists:
            return 'owner_deleted_rebuilt_row'
        snapshot = coll.document(cid).get()
        stamp = (snapshot.to_dict() or {}).get('v3_rederive_live_run') if snapshot.exists else None
        if stamp not in (None, run_id):
            return 'undo_newer_run_first'
    return None


def undo_live_rederive(uid, token, run_id, entries, *, firestore_client=None):
    """Restore one source-connected group of a live re-derive exactly, in one transaction.

    ``entries`` are the run's priors: ``raw`` (the row as stored before the run), or ``created`` for a
    row the run made, plus ``claims`` (each claim the row held, with its source and list position).
    Only rows still stamped by this run are restored; their sources get back exactly the claims they
    had, in place. Refuses when a newer run restamped a row or the owner deleted one since.
    """
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    held = leases.lease_ref(client, uid, store.BACKFILL_LEASE)
    deleted = client.collection('users').document(uid).collection('deleted_conversations')
    ids = [e['id'] for e in entries]

    @firestore.transactional
    def undo(tx):
        lease = held.get(transaction=tx).to_dict() or {}
        docs = {cid: coll.document(cid).get(transaction=tx) for cid in ids}
        tombstones = {cid: deleted.document(cid).get(transaction=tx) for cid in ids}
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
            raise Conflict('lease_lost')
        current = {cid: (snapshot.to_dict() or {}) if snapshot.exists else None for cid, snapshot in docs.items()}
        if any(t.exists for t in tombstones.values()):
            raise Conflict('owner_deleted_rebuilt_row')
        if any(row and row.get('v3_rederive_live_run') not in (None, run_id) for row in current.values()):
            raise Conflict('undo_newer_run_first')
        ours = {cid for cid, row in current.items() if row and row.get('v3_rederive_live_run') == run_id}
        rids = {c['recording_id'] for e in entries if e['id'] in ours for c in e.get('claims') or []}
        rids.update(rid for cid in ours for rid in (current[cid] or {}).get('v3_recording_ids') or [])
        rids.update(rid for e in entries if e['id'] in ours for rid in e.get('sources') or [])
        sources = {rid: coll.document(rid).get(transaction=tx) for rid in sorted(rids)}
        restored = removed = 0
        for entry in entries:
            if entry['id'] not in ours:
                continue
            if entry.get('created'):
                tx.delete(coll.document(entry['id']))
                removed += 1
            else:
                tx.set(coll.document(entry['id']), entry['raw'])
                restored += 1
        repaired = 0
        for rid, snapshot in sources.items():
            if not snapshot.exists:
                continue
            claims = (snapshot.to_dict() or {}).get('claims') or []
            kept = [c for c in claims if c.get('conversation_id') not in ours]
            back = sorted(
                (
                    (c['index'], c['claim'])
                    for e in entries
                    if e['id'] in ours and not e.get('created')
                    for c in e.get('claims') or []
                    if c['recording_id'] == rid
                ),
                key=lambda pair: pair[0],
            )
            for index, claim in back:
                kept.insert(min(index, len(kept)), claim)
            if kept != claims:
                tx.update(coll.document(rid), {'claims': kept})
                repaired += 1
        return {'rows_restored': restored, 'rows_removed': removed, 'sources_repaired': repaired}

    return undo(client.transaction())
