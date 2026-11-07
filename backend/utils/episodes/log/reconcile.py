"""Full authoritative repair after dropped capture. Capacity failure stays on legacy."""

from database import episode_log as store, episodes
from utils.episodes.log.backfill import events_for
from utils.episodes.log.fold import Fold
from utils.episodes.log.facts import compact_events


def source_documents(uid, client, *, transaction=None):
    """Bounded source read, also used inside publication to lock its proof.

    Compare SDK update_time, not application clocks: this detects deletes,
    inserts, receipt archive edits and writers that do not touch updated_at.
    """
    root = store.root(client, uid)
    documents = []
    for namespace in ('episodes', 'episode_links', 'episode_segment_receipts'):
        remaining = store.MAX_PUBLISH_ROWS - len(documents)
        page = list(root.collection(namespace).limit(remaining + 1).stream(transaction=transaction))
        documents.extend(page)
        if len(documents) > store.MAX_PUBLISH_ROWS:
            raise store.ProjectionCapacity('episode_reconcile_capacity')
        if namespace == 'episode_segment_receipts':
            for doc in page:
                shards = int((doc.to_dict() or {}).get('shards', 0))
                if shards > store.MAX_PUBLISH_ROWS - len(documents):
                    raise store.ProjectionCapacity('episode_reconcile_capacity')
                for index in range(shards):
                    documents.append(doc.reference.collection('s').document(str(index)).get(transaction=transaction))
    return documents


def versions(documents):
    return {doc.reference.path: doc.update_time for doc in documents}


def verify(uid, client, expected, transaction):
    # These reads MUST be inside the transaction that clears capture_dirty.
    # Firestore serializes later writers against these source reads as well.
    current = versions(source_documents(uid, client, transaction=transaction))
    if expected is not None:
        prefix = f'users/{uid}/conversations/'
        if current != {path: version for path, version in expected.items() if not path.startswith(prefix)}:
            # Reject source growth before member reads, retaining the shared
            # source-proof read bound even when new episodes were inserted.
            raise store.LostLease('episode_reconcile_source_changed_during_read')
        refs = [client.document(path) for path in expected if path.startswith(prefix)]
        # get_all retains missing documents (update_time=None). Read versions in
        # the publication transaction, never from a later nontransactional read.
        if refs:
            current.update(versions(client.get_all(refs, field_paths=[], transaction=transaction)))
    if expected is None or current != expected:
        raise store.LostLease('episode_reconcile_source_changed_during_read')


def read_members(uid, rows, client, proof):
    """Use the exact projected snapshots, within the shared repair read budget."""
    from utils.episodes import home_read

    ids = {cid for row in rows for cid in row.get('conversation_ids') or []}
    if len(proof) + len(ids) > store.MAX_PUBLISH_ROWS:
        raise store.ProjectionCapacity('episode_reconcile_capacity')
    return home_read.read_members(uid, rows, firestore_client=client, source_versions=proof)


def snapshot(uid, client):
    fold = Fold(uid)
    root = store.root(client, uid)
    budget = store.MAX_PUBLISH_ROWS

    def page(collection):
        nonlocal budget
        docs = list(collection.limit(budget + 1).stream())
        budget -= len(docs)
        if budget < 0:
            raise store.ProjectionCapacity('episode_reconcile_capacity')
        return docs

    documents = source_documents(uid, client)
    budget -= len(documents)
    for doc in documents:
        namespace = doc.reference.parent.id
        row = doc.to_dict() or {}
        if namespace == 'episodes':
            row = episodes.unseal(uid, row)
            if row is None:
                raise store.ProjectionCapacity('episode_reconcile_unreadable_row')
        doc_id = doc.reference.parent.parent.id if namespace == 's' else doc.id
        for event in compact_events(events_for('receipt_archive' if namespace == 's' else namespace, doc_id, row)):
            fold.apply(event)
    # Replace the whole projection, including deletion of stale rows and links.
    views = {doc.id for doc in page(root.collection('episode_views'))}
    links = {doc.id for doc in page(root.collection('episode_view_links'))}
    return fold, views - fold.rows().keys(), links - fold.links.keys(), versions(documents)
