"""Live re-derive reads and undo for the per-owner v3 repair tool (utils/conversations/v3/backfill.py).

One owner's finished live v3 windows in [since, until) are replanned from their source recordings by
the live planner after a planner fix. Only rows nobody else owns are offered as open priors; every
other row the loaded sources touch is offered as a published finished row, so its speech, claims and
audio stay exactly where they are, and it is never written. The projection commit itself stays in
database/conversations_v3.py (commit_projection's ``retire``). Runbook: docs/runbooks/conversations-v3.md.
"""

import hashlib
import json
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.conversations import ACTION_ITEMS_EDIT_REVISION, EVENTS_EDIT_REVISION, has_created_calendar_events
from database.conversations_v3_undo_removals import removal_ref
from database.home_feed_fields import COMMIT_STAMPED_FIELDS
from database.recurring_voice_privacy import filter_processing_write
from database.transcript_pointer import TranscriptBlobAbsent, TranscriptShredded
from utils.conversations.v3 import Conflict, policy

# Documents (sources and rows) one partition's started_at read may return; more blocks the partition.
REDERIVE_LIVE_LIMIT = 256
# A source whose stored document (by the same JSON estimate the projection's size log uses) is this
# close to Firestore's 1 MiB document limit cannot take a claims update safely: its rows stay as they
# are, and the dry-run reports it. CLAIM_BYTES is the estimate for one claim entry.
SOURCE_MAX_BYTES = 1_000_000
CLAIM_BYTES = 120


def stored_bytes(value):
    """The projection's JSON size estimate (database.conversations_v3 size log) for a stored value."""
    return len(json.dumps(value, default=str).encode())


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
    ACTION_ITEMS_EDIT_REVISION,
    EVENTS_EDIT_REVISION,
)


def live_row_protection(raw, *, since, until, run_id=None):
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
    if any(raw.get(field) for field in OWNER_EDIT_FIELDS) or summary_edited(raw):
        return 'edited'
    structured = raw.get('structured')
    if isinstance(structured, dict) and structured.get('action_items'):
        # Historical items can contain owner edits with no revision marker.
        return 'action_items'
    if has_created_calendar_events(structured):
        return 'calendar_events'
    if raw.get('apps_results'):
        # App results can be edited by the owner with no marker, and a replan never regenerates them.
        return 'app_results'
    if raw.get('discarded'):
        return 'discarded'
    # A row this run already wrote (an interrupted multi-batch commit, then resume) owes its notes on
    # the run's own marker, drained after the partition commits; it is replanned like any other.
    ours = run_id is not None and raw.get('v3_rederive_live_run') == run_id
    if (
        raw.get('v3_process_pending')
        or (raw.get('v3_backfill_process_pending') and not ours)
        or raw.get('tile_state') == 'transcribing'
        or raw.get('status') not in ('completed', 'processing', 'failed')
    ):
        return 'notes_pending'
    return None


def summary_edited(raw):
    """The owner rewrote the summary: the summary edit endpoint deletes generated sections.

    Older edits carry no separate marker, so a written card with an overview and no sections is
    treated as edited (the rule refinement applies to locked cards).
    """
    if not raw.get('v3_notes_written'):
        return False
    structured = raw.get('structured') if isinstance(raw.get('structured'), dict) else {}
    sections = structured.get('sections')
    return bool(structured.get('overview')) and not (isinstance(sections, list) and sections)


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
    if stored_bytes(raw) + 4 * CLAIM_BYTES > SOURCE_MAX_BYTES:
        return 'size_limit'
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
        raise Conflict('rederive_live_range_overflow')
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
        if not raws[rid].get('claims'):
            # Live speech no window ever claimed: the replan makes a card of it (reported, not hidden).
            count('sources_unclaimed')
        recordings[rid] = {
            **row,
            '_v3_rederive_live': True,
            '_v3_stored_bytes': stored_bytes(raws[rid]),
            '_v3_stored_claims_bytes': stored_bytes(raws[rid].get('claims') or []),
        }
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
        reason = live_row_protection(raw, since=since, until=until, run_id=run_id)
        # A deleted row is offered too: until its claims are released they still fence its speech.
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


# What the owner can change on a conversation (edits, sharing, lock, folder, summary text, app results)
# and what a merge or deletion changes. Undo refuses when any of it moved after the run.
OWNER_SURFACE_FIELDS = (
    *OWNER_EDIT_FIELDS,
    'data_protection_level',
    'visibility',
    'is_locked',
    'deleted',
    'discarded',
    'sync_merged_into',
    'folder_id',
    'apps_results',
)


def owner_surface(row):
    """A digest of the owner-changeable surface of a stored row (never content in the ledger)."""
    structured = row.get('structured') if isinstance(row.get('structured'), dict) else {}
    surface = {field: row.get(field) for field in OWNER_SURFACE_FIELDS}
    # Keep baselines for rows with no owner-managed embedded state compatible with existing runs.
    for revision_field in (ACTION_ITEMS_EDIT_REVISION, EVENTS_EDIT_REVISION):
        if not surface[revision_field]:
            surface.pop(revision_field)
    surface['structured'] = {k: structured.get(k) for k in ('title', 'overview')}
    if structured.get('action_items'):
        surface['structured']['action_items'] = structured['action_items']
    if row.get(EVENTS_EDIT_REVISION) or has_created_calendar_events(structured):
        surface['structured']['events'] = structured.get('events')
    return hashlib.sha256(json.dumps(surface, sort_keys=True, default=str).encode()).hexdigest()


def owner_changed(row, entry):
    """The owner (or a merge) acted on a row the run wrote, created or retired, after the run.

    Once the run's partition settled its notes, the row's owner surface is compared with the digest
    recorded then (``baseline``). Before that, the fields the run itself never sets are compared with
    the prior document, and a retired row must still be the run's bridge to its survivor.
    """
    raw = entry.get('raw') or {}
    if any(row.get(field) != raw.get(field) for field in (ACTION_ITEMS_EDIT_REVISION, EVENTS_EDIT_REVISION)):
        return True
    if entry.get('baseline'):
        return owner_surface(row) != entry['baseline']
    if has_created_calendar_events(row.get('structured')):
        return True
    if entry.get('retired_into'):
        return row.get('sync_merged_into') != entry['retired_into'] or not row.get('deleted')
    if row.get('sync_merged_into') or row.get('deleted'):
        return True
    if any(row.get(field) and row.get(field) != raw.get(field) for field in OWNER_EDIT_FIELDS):
        return True
    if summary_edited(row):
        return True
    if row.get('visibility') not in (None, 'private') and row.get('visibility') != raw.get('visibility'):
        return True
    if row.get('data_protection_level', 'standard') != raw.get('data_protection_level', 'standard'):
        return True
    return bool(row.get('is_locked')) and not raw.get('is_locked')


# The baseline of a row the owner changed before its partition settled: never equals a digest.
CHANGED_BEFORE_SETTLE = 'changed_before_settle'


def already_undone(row, entry, run_id):
    """This run's undo already handled the row: restored to its prior, or hidden awaiting erasure.

    The Firestore commit hook stamps home feed versions onto every conversation write, so a restored
    row equals its prior apart from those fields.
    """
    if row is None:
        return True
    if entry.get('created'):
        return row.get('v3_rederive_live_undone') == run_id
    return _unstamped(row) == _unstamped(entry.get('raw') or {})


def _unstamped(row):
    return {k: v for k, v in row.items() if k not in COMMIT_STAMPED_FIELDS}


# A prior the owner's deletion or protection change emptied: the run can no longer be undone exactly.
PURGED_REASONS = {'deleted': 'owner_deleted_rebuilt_row', 'protection': 'owner_edited_rebuilt_row'}


def purged_reason(entries):
    for entry in entries:
        if entry.get('purged'):
            return PURGED_REASONS.get(entry['purged'], 'owner_edited_rebuilt_row')
    return None


def _run_priors(uid, run_id, ids, client):
    """A partition's own copies by id, so a long run reads each copy a bounded number of times."""
    if ids is None:
        return runs.list_priors(uid, run_id, firestore_client=client)
    return runs.get_priors(uid, run_id, ids, firestore_client=client)


def record_baselines(uid, run_id, ids=None, *, firestore_client=None):
    """After a partition settles its notes, digest the owner surface of every row the run stamped.

    ``ids`` are the partition's copies (every copy of the run when None). A row the owner already
    changed between the commit and now (checked against the prior, as before a baseline exists)
    gets a baseline that never matches, so undo keeps refusing it.
    """
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    pending = [e for e in _run_priors(uid, run_id, ids, client) if not e.get('baseline') and not e.get('purged')]
    recorded = 0
    for start in range(0, len(pending), runs.PRIORS_PAGE_DOCS):
        page = pending[start : start + runs.PRIORS_PAGE_DOCS]

        @firestore.transactional
        def record(tx, page=page):
            rows = {e['id']: coll.document(e['id']).get(transaction=tx) for e in page}
            count = 0
            for entry in page:
                snapshot = rows[entry['id']]
                row = (snapshot.to_dict() or {}) if snapshot.exists else {}
                if row.get('v3_rederive_live_run') != run_id:
                    continue
                ref = runs.run_ref(client, uid, run_id).collection(runs.PRIORS).document(entry['id'])
                baseline = CHANGED_BEFORE_SETTLE if owner_changed(row, entry) else owner_surface(row)
                tx.update(ref, {'baseline': baseline})
                count += 1
            return count

        recorded += record(client.transaction())
    return recorded


# Firestore caps a transaction at 500 writes and about 10 MiB; an undo group restores in one.
UNDO_GROUP_BYTES = 8_000_000
# A source's rewritten claims list, at most (the commit's own size guard bounds it far lower).
SOURCE_CLAIMS_BYTES = 64_000


def undo_group_fits(entries):
    """One undo group's restore (rows, their sources and the lease reads) fits one transaction."""
    sources = {c['recording_id'] for e in entries for c in e.get('claims') or []}
    sources.update(rid for e in entries for rid in e.get('sources') or [])
    size = sum(stored_bytes(e.get('raw') or {}) + stored_bytes(e.get('claims') or []) for e in entries)
    size += len(sources) * SOURCE_CLAIMS_BYTES
    writes = len(entries) + len(sources) + sum(bool(entry.get('created')) for entry in entries)
    return writes < store.BATCH_MAX_WRITES and size <= UNDO_GROUP_BYTES


def drop_unwritten_priors(uid, run_id, entries, *, firestore_client=None):
    """Keep copies only of rows a run has stamped since the copy; drop the rest.

    A row no run stamped after its copy (its stamp is still the copy's) was never written by this
    run, or was already restored by its undo; a row that is gone has nothing to restore. So every
    kept copy belongs to a row a run stamped, which the deletion and protection paths reach, and a
    row a newer run restamped keeps its copy, so undo still waits for that run.
    """
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    unwritten = []
    for entry in entries:
        if entry.get('purged'):
            continue
        snapshot = coll.document(entry['id']).get()
        row = (snapshot.to_dict() or {}) if snapshot.exists else None
        stamp = (row or {}).get('v3_rederive_live_run')
        if row is None or (not entry.get('created') and stamp == (entry.get('raw') or {}).get('v3_rederive_live_run')):
            unwritten.append(entry['id'])
    if unwritten:
        runs.drop_priors(uid, run_id, unwritten, firestore_client=client)
    return len(unwritten)


def drop_stale_priors(uid, run_id, ids=None, *, firestore_client=None):
    """Before an attempt or an undo: drop this run's copies of rows it never stamped.

    A process that stopped between recording copies and stamping their rows leaves such copies;
    undo never restores an unstamped row, so they are only ever retained content. A partition's
    attempt checks the rows it loaded (``ids``); resume and undo check every copy of the run.
    """
    client = firestore_client or store.get_firestore_client()
    entries = _run_priors(uid, run_id, ids, client)
    return drop_unwritten_priors(uid, run_id, entries, firestore_client=client) if entries else 0


def live_undo_blocker(uid, run_id, entries, *, firestore_client=None):
    """Checked before any group restores, so a refusal leaves the run whole (each group re-checks)."""
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    deleted = client.collection('users').document(uid).collection('deleted_conversations')
    if purged_reason(entries):
        return purged_reason(entries)
    named = set()
    created = []
    for entry in entries:
        cid = entry['id']
        if deleted.document(cid).get().exists:
            return 'owner_deleted_rebuilt_row'
        snapshot = coll.document(cid).get()
        row = (snapshot.to_dict() or {}) if snapshot.exists else None
        if (
            row is not None
            and entry.get('created')
            and (row.get('v3_rederive_live_run') == run_id or row.get('v3_rederive_live_undone') == run_id)
        ):
            created.append(cid)
        if already_undone(row, entry, run_id):
            continue
        row = row or {}
        stamp = row.get('v3_rederive_live_run')
        if stamp not in (None, run_id):
            return 'undo_newer_run_first'
        if stamp == run_id and owner_changed(row, entry):
            return 'owner_edited_rebuilt_row'
        if stamp == run_id:
            named.update(c['recording_id'] for c in entry.get('claims') or [])
            named.update(entry.get('sources') or [])
    if created and store.merge_donors_have_tasks(uid, created, firestore_client=client):
        return 'undo_created_row_has_tasks'
    # Every source any group will repair, before the first group restores.
    if any(not coll.document(rid).get().exists for rid in sorted(named)):
        return 'undo_source_missing'
    return None


def undo_live_rederive(uid, held_leases, run_id, entries, *, firestore_client=None):
    """Restore one source-connected group of a live re-derive exactly, in one transaction.

    ``entries`` are the run's priors: ``raw`` (the row as stored before the run), or ``created`` for a
    row the run made, plus ``claims`` (each claim the row held, with its source and list position).
    Only rows still stamped by this run are restored; their sources get back exactly the claims they
    had, in place. A created row is hidden here (retired, with no claims) and returns its id in
    ``created`` for the caller to erase with the conversation deletion helper, which also removes its
    child collections. Refuses when a newer run restamped a row, or the owner deleted or edited one.
    """
    client = firestore_client or store.get_firestore_client()
    coll = store.user_conversations(client, uid)
    lease_refs = [(leases.lease_ref(client, uid, key), token) for key, token in held_leases]
    deleted = client.collection('users').document(uid).collection('deleted_conversations')
    ids = [e['id'] for e in entries]

    @firestore.transactional
    def undo(tx):
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('wipe_status')
        ):
            raise Conflict('account_deletion')
        docs = {cid: coll.document(cid).get(transaction=tx) for cid in ids}
        tombstones = {cid: deleted.document(cid).get(transaction=tx) for cid in ids}
        current = {cid: (snapshot.to_dict() or {}) if snapshot.exists else None for cid, snapshot in docs.items()}
        if purged_reason(entries):
            raise Conflict(purged_reason(entries))
        if any(t.exists for t in tombstones.values()):
            raise Conflict('owner_deleted_rebuilt_row')
        by_id = {e['id']: e for e in entries}
        # An interrupted earlier attempt of this undo: rows it restored or hid are done, not conflicts.
        done = {cid for cid, row in current.items() if already_undone(row, by_id[cid], run_id)}
        if any(
            row.get('v3_rederive_live_run') not in (None, run_id)
            for cid, row in current.items()
            if cid not in done and row
        ):
            raise Conflict('undo_newer_run_first')
        ours = {
            cid for cid, row in current.items() if cid not in done and row and row.get('v3_rederive_live_run') == run_id
        }
        if any(owner_changed(current[cid] or {}, by_id[cid]) for cid in ours):
            raise Conflict('owner_edited_rebuilt_row')
        created = [cid for cid in sorted(ours | done) if current[cid] is not None and by_id[cid].get('created')]
        if created and store.merge_donors_have_tasks(uid, created, firestore_client=client, transaction=tx):
            raise Conflict('undo_created_row_has_tasks')
        # A recurring voice the owner revoked since the run is never written back.
        user = client.collection('users').document(uid)
        restore = {}
        for entry in entries:
            if entry['id'] in ours and not entry.get('created'):
                restore[entry['id']] = dict(entry['raw'])
                filter_processing_write(tx, user, restore[entry['id']])
        rids = {c['recording_id'] for e in entries if e['id'] in ours for c in e.get('claims') or []}
        rids.update(rid for cid in ours for rid in (current[cid] or {}).get('v3_recording_ids') or [])
        rids.update(rid for e in entries if e['id'] in ours for rid in e.get('sources') or [])
        sources = {rid: coll.document(rid).get(transaction=tx) for rid in sorted(rids)}
        if any(not snapshot.exists for snapshot in sources.values()):
            # A source the run's claims name is gone: the rows cannot get their claims back.
            raise Conflict('undo_source_missing')
        for ref, token in lease_refs:
            lease = ref.get(transaction=tx).to_dict() or {}
            if lease.get('token') != token or not lease.get('until') or lease['until'] <= datetime.now(timezone.utc):
                raise Conflict('lease_lost')
        restored = 0
        for cid in created:
            # Commit the fence before erasure, including resumed undos for an already-hidden row.
            tx.set(removal_ref(user, cid), {'removed_by_undo': True})
        for entry in entries:
            if entry['id'] not in ours:
                continue
            if entry.get('created'):
                tx.update(
                    coll.document(entry['id']),
                    {
                        'deleted': True,
                        'discarded': True,
                        'v3_derived': False,
                        'home_hidden': True,
                        'v3_rederive_live_undone': run_id,
                    },
                )
            else:
                tx.set(coll.document(entry['id']), restore[entry['id']])
                restored += 1
        repaired = 0
        for rid, snapshot in sources.items():
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
        return {'rows_restored': restored, 'created': created, 'sources_repaired': repaired}

    return undo(client.transaction())
