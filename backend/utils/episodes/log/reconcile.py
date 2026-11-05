"""Full authoritative repair after dropped capture. Capacity failure stays on legacy."""

from database import episode_log as store, episodes
from utils.episodes.log.backfill import events_for
from utils.episodes.log.fold import Fold
from utils.episodes.log.facts import compact_events


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

    for namespace in ('episodes', 'episode_links', 'episode_segment_receipts'):
        for doc in page(root.collection(namespace)):
            row = doc.to_dict() or {}
            if namespace == 'episodes':
                row = episodes.unseal(uid, row)
                if row is None:
                    raise store.ProjectionCapacity('episode_reconcile_unreadable_row')
            for event in compact_events(events_for(namespace, doc.id, row)):
                fold.apply(event)
            if namespace == 'episode_segment_receipts':
                shards = int(row.get('shards', 0))
                if shards > budget:
                    raise store.ProjectionCapacity('episode_reconcile_capacity')
                budget -= shards
                for index in range(shards):
                    archive = doc.reference.collection('s').document(str(index)).get().to_dict() or {}
                    for event in compact_events(events_for('receipt_archive', doc.id, archive)):
                        fold.apply(event)
    # Replace the whole projection, including deletion of stale rows and links.
    views = {doc.id for doc in page(root.collection('episode_views'))}
    links = {doc.id for doc in page(root.collection('episode_view_links'))}
    return fold, views - fold.rows().keys(), links - fold.links.keys()
