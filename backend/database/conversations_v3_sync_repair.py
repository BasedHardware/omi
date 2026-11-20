"""Version-fenced operational repair for one explicitly nominated redirect chain."""

import hashlib
import json
import re

from google.cloud import firestore

from database import conversations
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.transcript_pointer import TranscriptBlobAbsent, TranscriptShredded
from utils.conversations.size_limit import CONVERSATION_ABSORPTION_BYTE_CAP, projected_document_bytes
from utils.conversations.v3 import sync_custody

COLLECTION = 'conversations_v3_sync_custody_repairs'


def _valid_id(value):
    return isinstance(value, str) and bool(value) and '/' not in value and value not in {'.', '..'}


def _digest(value):
    encoded = json.dumps(value, default=str, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _version(snapshot):
    return snapshot.update_time.rfc3339()


def _write_patch(tx, ref, patch):
    if 'claims' in patch:
        tx.update(ref, {'claims': patch['claims']})
    else:
        tx.update(ref, {'v3_recording_ids': patch['v3_recording_ids']})


def repair(client, uid, donor_id, *, mode='preview', receipt=None):
    if not _valid_id(uid) or not _valid_id(donor_id):
        raise ValueError('one owner and one donor document id are required')
    if mode not in {'preview', 'apply', 'rollback'}:
        raise ValueError('unknown repair mode')
    if mode != 'preview' and (not isinstance(receipt, str) or not re.fullmatch(r'[0-9a-f]{64}', receipt)):
        raise ValueError('apply and rollback require a preview receipt')

    owner = client.collection('users').document(uid)
    coll = owner.collection('conversations')
    tombstones = owner.collection('deleted_conversations')
    journal = owner.collection(COLLECTION).document(receipt) if receipt else None

    @firestore.transactional
    def run(tx):
        marker = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        if account_deletion_marker_blocks_access(
            marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
        ):
            raise sync_custody.CustodyBlocked('account_deletion')

        snapshots = {}

        def read(cid):
            if not _valid_id(cid):
                raise sync_custody.CustodyBlocked('invalid_source')
            if cid not in snapshots:
                if tombstones.document(cid).get(transaction=tx).exists:
                    raise sync_custody.CustodyBlocked('tombstoned')
                snapshot = coll.document(cid).get(transaction=tx)
                if not snapshot.exists or not snapshot.update_time:
                    raise sync_custody.CustodyBlocked('document_unavailable')
                snapshots[cid] = snapshot
            return snapshots[cid].to_dict()

        def decode(cid, row):
            try:
                segments = conversations.decode_transcript_segments_verified(
                    uid, row.get('transcript_segments') or [], bool(row.get('transcript_segments_compressed'))
                )
            except (TypeError, ValueError, TranscriptBlobAbsent, TranscriptShredded):
                raise sync_custody.CustodyBlocked('speech_unavailable') from None
            return {**row, 'id': cid, 'transcript_segments': segments}

        recorded = journal.get(transaction=tx) if journal is not None else None
        if recorded is not None and recorded.exists:
            state = recorded.to_dict()
            if state['donor'] != donor_id:
                raise sync_custody.CustodyBlocked('receipt_scope_changed')
            if mode in {'preview', 'apply'} or state['outcome'] == 'rolled_back':
                return {'outcome': state['outcome'], 'receipt': receipt}
            prior = state['prior']
            for cid, version in state['unchanged'].items():
                read(cid)
                if _version(snapshots[cid]) != version:
                    raise sync_custody.CustodyBlocked('changed_since_apply')
            for cid in prior:
                read(cid)
                # All changed documents and the journal share one commit timestamp.
                if _version(snapshots[cid]) != _version(recorded):
                    raise sync_custody.CustodyBlocked('changed_since_apply')
            for cid, fields in prior.items():
                _write_patch(
                    tx,
                    coll.document(cid),
                    {
                        field: saved['value'] if saved['present'] else firestore.DELETE_FIELD
                        for field, saved in fields.items()
                    },
                )
            tx.update(
                journal,
                {'outcome': 'rolled_back', 'prior': firestore.DELETE_FIELD, 'unchanged': firestore.DELETE_FIELD},
            )
            return {'outcome': 'rolled_back', 'receipt': receipt}
        if mode == 'rollback':
            raise sync_custody.CustodyBlocked('unknown_receipt')

        path = {}
        cid = donor_id
        while True:
            if cid in path or len(path) > sync_custody.MAX_DONORS:
                raise sync_custody.CustodyBlocked('redirect_chain_budget_or_cycle')
            row = read(cid)
            target = row.get('sync_merged_into')
            if not target:
                if not path or row.get('deleted') or row.get('discarded'):
                    raise sync_custody.CustodyBlocked('missing_survivor')
                break
            if not row.get('deleted') or not row.get('recording') or row.get('smart_merge'):
                raise sync_custody.CustodyBlocked('unsupported_redirect')
            path[cid] = row
            cid = target
        if not set(path) <= set(row.get('sync_merged_from') or ()):
            raise sync_custody.CustodyBlocked('missing_lineage')

        donors = {rid: decode(rid, raw) for rid, raw in path.items() if raw.get('claims')}
        if not donors:
            if mode == 'apply':
                raise sync_custody.CustodyBlocked('preview_changed')
            return {'outcome': 'no_claims', 'chain': [*path, cid]}
        if any(raw.get('deleted_spans') for raw in path.values()):
            raise sync_custody.CustodyBlocked('deletion_custody')
        patches = sync_custody.transfer(decode(cid, row), donors, lambda card: decode(card, read(card)))
        prior = {}
        for rid, patch in patches.items():
            snapshot = snapshots[rid]
            raw = snapshot.to_dict()
            if projected_document_bytes(snapshot.reference, patch, raw) > CONVERSATION_ABSORPTION_BYTE_CAP:
                raise sync_custody.CustodyBlocked('document_size_budget')
            prior[rid] = {field: {'present': field in raw, 'value': raw.get(field)} for field in patch}
        chain = [*path, cid]
        revisions = {rid: _version(snap) for rid, snap in snapshots.items()}
        journal_data = {
            'donor': donor_id,
            'outcome': 'applied',
            'prior': prior,
            'unchanged': {rid: version for rid, version in revisions.items() if rid not in patches},
        }
        if projected_document_bytes(owner.collection(COLLECTION).document('0' * 64), journal_data, None) > 128 * 1024:
            raise sync_custody.CustodyBlocked('journal_size_budget')
        token = _digest(
            {
                'version': 1,
                'project': client.project,
                'uid': uid,
                'chain': chain,
                'revisions': revisions,
                'patches': patches,
            }
        )
        if mode == 'preview':
            return {'outcome': 'ready', 'receipt': token, 'chain': chain, 'prior': prior, 'patches': patches}
        if receipt != token:
            raise sync_custody.CustodyBlocked('preview_changed')
        for rid, patch in patches.items():
            _write_patch(tx, coll.document(rid), patch)
        tx.create(journal, journal_data)
        return {'outcome': 'applied', 'receipt': token}

    try:
        return run(client.transaction(max_attempts=3, read_only=mode == 'preview'))
    except sync_custody.CustodyBlocked as error:
        return {'outcome': 'skipped', 'reason': str(error)}
