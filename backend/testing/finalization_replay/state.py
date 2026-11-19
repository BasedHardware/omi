"""Seed and inspect the Firestore state visible at the finalization boundary."""

from __future__ import annotations

from testing.finalization_replay.corpus import pack, seed_document

# Python stores its queue and queue metrics projection in Firestore. Go stores
# the queue in Postgres. The disposition is compared separately from these rows.
QUEUE_COLLECTIONS = {'conversation_finalization_jobs', 'conversation_finalization_projection_shards'}


def _documents(collection):
    # list_documents also returns missing parents that own populated subcollections.
    for ref in collection.list_documents():
        snapshot = ref.get()
        if snapshot.exists:
            yield ref.path, snapshot.to_dict()
        for child in ref.collections():
            yield from _documents(child)


class CaseState:
    def __init__(self, client, case):
        self.client = client
        self.case = case
        self.uid = case.get('uid', f'replay-{case["name"]}')
        self.cid = case.get('conversation_id', case['name'])
        self.user = client.collection('users').document(self.uid)
        self.conversation = self.user.collection('conversations').document(self.cid)
        self.notes = case.get('notes', {'title': 'Synthetic replay', 'overview': 'Review the synthetic agenda.'})
        self.apps = case.get('apps', [])
        self.memories = case.get('memories', [])
        self.webhooks = []
        self.version = 1

    def seed(self):
        self.user.set(
            {
                'data_protection_level': 'standard',
                'byok': {'active': self.case.get('own_key', False)},
            }
        )
        doc = seed_document(self.case, self.cid)
        if doc is not None:
            self.conversation.set(doc)

    def documents(self):
        return {
            path: pack(row)
            for collection in self.client.collections()
            if collection.id not in QUEUE_COLLECTIONS
            for path, row in _documents(collection)
            if path != self.conversation.path
        }

    def observe(self, status, before):
        after = self.documents()
        changed = {
            path: after.get(path)
            for path in sorted(before.keys() | after.keys())
            if before.get(path) != after.get(path)
        }
        return {
            'status': status,
            'conversation': pack(self.conversation.get().to_dict()),
            'derived_documents': changed,
            'webhooks': sorted(self.webhooks, key=lambda delivery: delivery['app']),
        }

    def vector(self, overview):
        self.user.collection('replay_vectors').document(self.cid).set({'overview': overview})

    def memory(self, memory_id, content, protection):
        self.user.collection('replay_memories').document(memory_id).set(
            {
                'content': content,
                'data_protection_level': protection,
            }
        )

    def webhook(self, app, key, payload):
        self.webhooks.append(
            {
                'app': app,
                'conversation_id': self.cid,
                'idempotency_key': key,
                'payload': pack(payload),
            }
        )
