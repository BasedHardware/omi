"""Seed and inspect the Firestore state visible at the finalization boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from testing.finalization_replay.corpus import FIXED_DATE, pack, seed_document

# Python stores its queue and queue metrics projection in Firestore. Go stores
# the queue in Postgres. The disposition is compared separately from these rows.
QUEUE_COLLECTIONS = {'conversation_finalization_jobs', 'conversation_finalization_projection_shards'}


def _same_snapshot_value(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_snapshot_value(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_same_snapshot_value(a, b) for a, b in zip(left, right, strict=True))
    return left == right


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
        self.llm_tokens = {'prompt': 0, 'completion': 0}
        self.embedding_tokens = 0
        self.firestore_operations = {
            'rpc_calls': 0,
            'document_reads': 0,
            'query_documents': 0,
            'query_requests': 0,
            'writes': 0,
            'deletes': 0,
        }
        self.go_evidence = {}
        self._metrics_lock = Lock()
        self.cost_measured = False
        self.replay_token_calls = []
        self.notes_prompt_hashes = []
        self.started_at = None

    def record_provider_call(self, feature, prompt, completion):
        from testing.finalization_replay.metrics import prompt_token_estimate, token_estimate

        prompt_tokens = prompt_token_estimate(prompt)
        completion_tokens = token_estimate(completion)
        with self._metrics_lock:
            self.provider_calls.append(feature)
            self.llm_tokens['prompt'] += prompt_tokens
            self.llm_tokens['completion'] += completion_tokens
        return prompt_tokens, completion_tokens

    def record_embedding_request(self, values):
        from testing.finalization_replay.metrics import embedding_token_estimate

        if not isinstance(values, list):
            values = [values]
        with self._metrics_lock:
            self.provider_calls.append('openai-embeddings')
            self.embedding_tokens += sum(embedding_token_estimate(value) for value in values)

    def add_firestore_operations(self, **counts):
        with self._metrics_lock:
            for name, count in counts.items():
                self.firestore_operations[name] += count

    def cost(self):
        with self._metrics_lock:
            prompt = self.llm_tokens['prompt']
            completion = self.llm_tokens['completion']
            return {
                'measured': self.cost_measured,
                'token_basis': 'cl100k content-token estimate; excludes model/API framing',
                'llm_tokens': {'prompt': prompt, 'completion': completion, 'total': prompt + completion},
                'embedding_tokens': self.embedding_tokens,
                'firestore_operations': dict(self.firestore_operations),
            }

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
            if not _same_snapshot_value(before.get(path), after.get(path))
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
            'cost': self.cost(),
            'go_evidence': self.go_evidence,
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
