"""Planning and undo bookkeeping for live re-derive partitions."""

import json
from datetime import timedelta

from database import conversations_v3 as store, conversations_v3_rederive as rederive_store
from utils.conversations.v3 import Conflict


def _held_claims(recordings, cid):
    """(recording id, list position, claim) for every claim the loaded sources hold for one row."""
    return [
        (rid, index, claim)
        for rid, recording in recordings.items()
        for index, claim in enumerate(recording.get('claims') or [])
        if isinstance(claim, dict) and claim.get('conversation_id') == cid
    ]


def _speech(row):
    return [(s.get('id'), s.get('start'), s.get('end'), s.get('text')) for s in row.get('transcript_segments') or []]


def _spoken(row):
    """Each stored segment of a row by recorded clock: (segment id, text, absolute start to 10 ms)."""
    keys = set()
    for s in row.get('transcript_segments') or []:
        try:
            at = row['started_at'] + timedelta(seconds=float(s.get('start') or 0))
        except (TypeError, ValueError, KeyError):
            continue
        keys.add((s.get('id'), ' '.join(str(s.get('text') or '').split()), round(at.timestamp(), 2)))
    return keys


def _same_window(row, original, held):
    """The rebuilt window has the stored row's speech, bounds, claims and Home decision: leave it alone."""
    if any(
        row.get(k) != original.get(k)
        for k in ('started_at', 'finished_at', 'kind', 'home_hidden', 'home_hidden_reason', 'manual_end')
    ):
        return False
    if _speech(row) != _speech(original):
        return False
    before = {}
    for rid, _index, claim in held:
        before.setdefault(rid, []).append((claim.get('start'), claim.get('end')))
    after = {rid: [(c['start'], c['end']) for c in spans] for rid, spans in row['_v3_claims'].items() if spans}
    return {k: sorted(v) for k, v in before.items()} == {k: sorted(v) for k, v in after.items()}


def _survivor(original, planned):
    """The rebuilt window that absorbed most of a retired row's time (earliest on a tie), if any."""
    start, end = original.get('started_at'), original.get('finished_at')
    best, best_overlap = None, None
    for row in sorted(planned, key=lambda r: r['started_at']):
        overlap = (min(end, row['finished_at']) - max(start, row['started_at'])).total_seconds()
        touches = overlap > 0 or row['started_at'] <= start <= row['finished_at']
        if touches and (best_overlap is None or overlap > best_overlap):
            best, best_overlap = row['id'], overlap
    return best


def _stored_bytes(value):
    """Mirrors rederive_store.stored_bytes, kept here so the async reconcile path stays pure."""
    return len(json.dumps(value, default=str).encode())


def _retire_patch(survivor, run_id, prior):
    """A retired live row becomes a sync bridge to the window that absorbed it.

    Deleted and discarded hide it everywhere a merged-away conversation is hidden, reads by id follow
    ``sync_merged_into`` to the survivor, and dropping ``v3_derived`` keeps every v3 planning read
    (closure claims, time queries, adoption) from treating it as a deletion tombstone.
    """
    return {
        'deleted': True,
        'discarded': True,
        # Owes no summary: the debt query must not keep selecting a row its repair refuses.
        'summary_due_at': None,
        'sync_merged_into': survivor,
        'v3_derived': False,
        'v3_rederive_live_run': run_id,
        # As a sync merge's absorbed row: its claims went to the survivor, so deleting the bridge later
        # releases nothing of the survivor's, and cached copies see the redirect.
        'v3_claims_transferred_to': survivor,
        'sync_content_revision': int(prior.get('sync_content_revision') or 0) + 1,
    }


def live_outcome(rows, existing, recordings, *, since, until, run_id):
    """Turn a live re-derive's planned rows into what it writes, retires and records for undo.

    Protected rows are never written. A rebuilt window equal to its stored row is not written (no
    notes re-run). A rebuilt window keeps the id of the earliest row it absorbs (service._match);
    every other eligible row it absorbs is retired into it. Returns (rows to write, retire patches,
    touched row ids, recordings to commit, undo priors, ledger counts).
    """
    protected = {cid for cid, row in existing.items() if row.get('_v3_protected')}
    eligible = {cid: row for cid, row in existing.items() if cid not in protected}
    planned = [row for row in rows if row['id'] not in protected]
    for row in planned:
        if row['status'] == 'in_progress':
            raise Conflict('rederive_live_open')
        if row['started_at'] < since or row['finished_at'] > until:
            raise Conflict('rederive_live_boundary')
    unchanged = {
        row['id']
        for row in planned
        if row['id'] in eligible
        and _same_window(row, eligible[row['id']]['_v3_original'], _held_claims(recordings, row['id']))
    }
    # Nothing a row said may disappear: every eligible row's speech is in a rebuilt or protected row.
    kept_speech = set().union(*(_spoken(row) for row in planned), *(_spoken(existing[cid]) for cid in protected))
    before_speech = set().union(*(_spoken(prior['_v3_original']) for prior in eligible.values()))
    if before_speech - kept_speech:
        raise Conflict('rederive_live_coverage')
    planned_ids = {row['id'] for row in planned}
    retire, kept = {}, 0
    for cid, prior in eligible.items():
        if cid in planned_ids:
            continue
        survivor = _survivor(prior['_v3_original'], planned)
        if survivor is None:
            # No rebuilt window covers its time: nothing absorbed it, so it stays as it is.
            kept += 1
            continue
        retire[cid] = _retire_patch(survivor, run_id, prior['_v3_raw'])
    # The survivor lists its bridges (sync_merged_from), as a sync merge does: deleting it purges them.
    # The list lands in the final batch with the retirements, never before the bridges exist.
    merged_from = {}
    for cid, patch in retire.items():
        donors = merged_from.setdefault(patch['sync_merged_into'], set())
        donors.add(cid)
        donors.update(eligible[cid]['_v3_raw'].get('sync_merged_from') or [])
    lineage = {}
    for row in planned:
        if row['id'] in merged_from:
            had = (eligible.get(row['id']) or {}).get('_v3_raw', {}).get('sync_merged_from') or []
            lineage[row['id']] = {'sync_merged_from': sorted({*had, *merged_from[row['id']]})}
    write = [row for row in planned if row['id'] not in unchanged or row['id'] in merged_from]
    touched = {row['id'] for row in write} | set(retire)
    sources = {rid for row in write for rid in row.get('v3_recording_ids') or []} & recordings.keys()
    sources |= {
        rid
        for rid, recording in recordings.items()
        if any(isinstance(c, dict) and c.get('conversation_id') in touched for c in recording.get('claims') or [])
    }
    for rid in sources:
        recording = recordings[rid]
        claims = [
            c
            for c in recording.get('claims') or []
            if not (isinstance(c, dict) and c.get('conversation_id') in touched)
        ]
        claims += [{'conversation_id': row['id'], **span} for row in write for span in row['_v3_claims'].get(rid) or []]
        stored = recording.get('_v3_stored_bytes', 0)
        after = stored - recording.get('_v3_stored_claims_bytes', 0) + _stored_bytes(claims)
        if after > stored and after > rederive_store.SOURCE_MAX_BYTES:
            # Growing a source past the document limit fails every retry; block before any write.
            raise Conflict('document_too_large')
    if len(sources) + 2 * len(retire) + len(lineage) + 2 > store.BATCH_MAX_WRITES:
        # Reserve a write for each retirement and its task-link marker, plus the lineage, row and lease.
        raise Conflict('backfill_partition_budget')
    new_sources = {row['id']: set(row.get('v3_recording_ids') or []) for row in write}
    priors = []
    for cid in sorted(touched):
        prior = eligible.get(cid)
        if prior is not None and prior['_v3_raw'].get('v3_rederive_live_run') == run_id:
            # Already this run's (a resumed partition): its first prior is the one undo restores.
            continue
        held = _held_claims(recordings, cid)
        entry = {
            'id': cid,
            'sources': sorted(new_sources.get(cid, set()) | {rid for rid, _i, _c in held}),
            'claims': [{'recording_id': rid, 'index': index, 'claim': claim} for rid, index, claim in held],
        }
        if prior is None:
            entry['created'] = True
        else:
            entry['raw'] = prior['_v3_raw']
        if cid in retire:
            entry['retired_into'] = retire[cid]['sync_merged_into']
        if _stored_bytes(entry) > rederive_store.SOURCE_MAX_BYTES:
            # The prior holds the whole stored row; one that cannot be written leaves no exact undo.
            raise Conflict('document_too_large')
        priors.append(entry)
    counts = {
        'windows_after': len(planned),
        'visible_after': sum(1 for row in planned if not row.get('home_hidden')),
        'rows_unchanged': len(unchanged),
        'rows_rebuilt': sum(1 for row in write if row['id'] in eligible),
        'rows_created': sum(1 for row in write if row['id'] not in eligible),
        'rows_retired': len(retire),
        'rows_kept_unabsorbed': kept,
        'priors_recorded': len(priors),
        # The partition's settle step baselines these rows' copies by id rather than listing the run's;
        # a resumed partition's rows the failed attempt already wrote keep their first copy.
        'prior_ids': sorted(touched),
        'segments_checked': len(before_speech),
    }
    return write, {**retire, **lineage}, touched, sources, priors, counts
