"""Seed and inspect the Firestore state visible at the finalization boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from testing.finalization_replay.corpus import FIXED_DATE, pack, seed_document

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
        self.admitted = None
        self.queue_fanout_key = None
        self.initial_updated_at = None
        self.effects = {}
        self.provider_calls = []
        self.started_at = None

    def seed(self, provider_url):
        self.user.set(
            {
                'data_protection_level': 'standard',
                'byok': {'active': self.case.get('own_key', False)},
            }
        )
        doc = seed_document(self.case, self.cid)
        if doc is not None:
            self.conversation.set(doc)
        self.seed_app_catalog(provider_url)

    def seed_app_catalog(self, provider_url):
        for app in self.apps:
            data = {
                'id': app,
                'uid': self.uid,
                'name': app,
                'private': True,
                'approved': True,
                'category': 'other',
                'author': 'Replay',
                'description': 'Synthetic replay app',
                'image': '',
                'capabilities': ['memories', 'external_integration'],
                'memory_prompt': 'Summarize the replay agenda.',
                'external_integration': {
                    'triggers_on': 'memory_creation',
                    'webhook_url': f'{provider_url}/receive/{app}',
                },
            }
            self.client.collection('plugins_data').document(app).create(data)
        if self.apps:
            self.user.collection('folders').document('replay-folder').set(
                {
                    'id': 'replay-folder',
                    'name': 'Replay',
                    'description': 'Replay planning',
                    'color': '#6366F1',
                    'icon': '📋',
                    'created_at': FIXED_DATE,
                    'updated_at': FIXED_DATE,
                    'is_default': True,
                    'conversation_count': 0,
                    'order': 0,
                }
            )
            self.user.collection('goals').document('replay-goal').set(
                {
                    'id': 'replay-goal',
                    'title': 'Review agendas',
                    'is_active': True,
                    'target_value': 10,
                    'current_value': 0,
                    'metric': 'agendas',
                    'created_at': FIXED_DATE,
                }
            )

    def documents(self):
        return {
            path: pack(row)
            for collection in self.client.collections()
            if collection.id not in QUEUE_COLLECTIONS
            for path, row in _documents(collection)
            if path != self.conversation.path
        }

    def start(self):
        self.initial_updated_at = (self.conversation.get().to_dict() or {}).get('updated_at')
        self.started_at = datetime.now(timezone.utc)

    def observe(self, status, before):
        after = self.documents()
        changed = {
            path: after.get(path)
            for path in sorted(before.keys() | after.keys())
            if before.get(path) != after.get(path)
        }
        document = self.conversation.get().to_dict()
        return {
            'status': status,
            'queue_fanout_key': self.queue_fanout_key,
            'updated_at_changed': (document or {}).get('updated_at') != self.initial_updated_at,
            'admitted': self.admitted,
            'started_at': self.started_at.isoformat(),
            'finished_at': datetime.now(timezone.utc).isoformat(),
            'provider_calls': sorted(self.provider_calls),
            'effects': pack(self.effects),
            'conversation': pack(document),
            'derived_documents': changed,
            'webhooks': sorted(self.webhooks, key=lambda delivery: delivery['app']),
        }

    def vector(self, conversation_id):
        self.effects.setdefault('conversation_vector', []).append({'conversation_id': conversation_id})

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
