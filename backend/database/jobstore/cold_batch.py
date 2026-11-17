"""Actual bounded record-group SDK commits; no new deadline, policy or authority."""

import math

from google.cloud import firestore

from database import rpc_deadline
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_privacy_attempt import TOKEN_FIELD, token_version
from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.cold_packet import packet_for, needs_write


def apply_rows(sink, rows, *, timeout):
    if not 1 <= len(rows) <= 100:
        raise AuthorityRefused('bounded original cold page required')
    if not math.isfinite(timeout) or timeout <= 0:
        raise TimeoutError('cold page not sent: explicit positive deadline required')
    with rpc_deadline.rpc_deadline(rpc_deadline.now() + timeout):
        rpc_deadline.bind_firestore_client(sink.handoff.client)
        groups = {}
        # Every exact journal body/census commits under its original owner X
        # before any FS request. Unsupported sources refuse the whole page.
        for row in rows:
            recording, original = sink._context(row)
            key = (recording, fingerprint(dict(intent=original['intent'], admission=original['admission'])))
            groups.setdefault(key, []).append((row, recording, original))
        for group in groups.values():
            _apply_group(sink, group)


def _apply_group(sink, group):
    client, namespace = sink.handoff.client, sink.handoff.ticket.namespace
    original, recording = group[0][2], group[0][1]
    through = max(row[0] for row, _, _ in group)

    @firestore.transactional
    def erased(transaction):
        sink.handoff.authority.check(transaction, phases=('PG_OPEN', 'PG_CLOSING', 'BOTH_CLOSED'))
        return sink._erased(transaction, recording, original, through)

    if erased(client.transaction()):
        return
    # A committed later image dominates earlier versions of this same original
    # key. Every dominated version was independently checked against PG above.
    latest = {}
    for row, _, _ in group:
        packet = packet_for(namespace, row, recording, original)
        ref = sink.ref(row[2], row[3])
        if ref.path not in latest or latest[ref.path][1]['seq'] < packet['seq']:
            latest[ref.path] = (ref, packet)
    admission = sink.admit_original(original)

    @firestore.transactional
    def put(transaction):
        sink.handoff.authority.check(transaction, phases=('PG_OPEN', 'PG_CLOSING', 'BOTH_CLOSED'))
        if sink._erased(transaction, recording, original, through):
            return
        token = client.collection('batch_pipeline_privacy').document(original['owner_key']).get(transaction=transaction)
        if token_version(token) is None or (token.to_dict() or {}).get(TOKEN_FIELD) != admission['privacy_token']:
            raise AuthorityRefused('cold copy privacy token changed')
        assert_batch_write_allowed(
            client,
            transaction,
            original['intent']['uid'],
            conversation_ids=original['intent']['conversation_ids'],
            expected_generation=original['admission']['fs_privacy_generation'],
            snapshots={},
        )
        previous = {}
        for snapshot in client.get_all([ref for ref, _ in latest.values()], transaction=transaction):
            if snapshot.reference.path not in latest or snapshot.reference.path in previous:
                raise ConnectionError('cold batch response census changed')
            previous[snapshot.reference.path] = snapshot.to_dict()
        if set(previous) != set(latest):
            raise ConnectionError('cold batch response census incomplete')
        # All reads precede all writes; one real guard covers precisely this
        # original recording's immutable paid targets and original deadlines.
        for path, (ref, packet) in latest.items():
            if needs_write(previous[path], packet):
                transaction.set(ref, packet)

    put(client.transaction())
