"""Seed and inspect the Firestore state visible at the finalization boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import re
from threading import Lock

from testing.finalization_replay.corpus import FIXED_DATE, pack, seed_document
from testing.finalization_replay.metrics import embedding_token_estimate, prompt_token_estimate, token_estimate

# Python stores its queue and queue metrics projection in Firestore. Go stores
# the queue in Postgres. The disposition is compared separately from these rows.
QUEUE_COLLECTIONS = {'conversation_finalization_jobs', 'conversation_finalization_projection_shards'}
TOKEN_HEX = re.compile(r'[0-9a-f]{32}')


def _seeded_tokens(value):
    """Collect UUID-shaped fixture values; generated Home tokens are UUIDv4 hex."""
    if isinstance(value, str):
        if TOKEN_HEX.fullmatch(value):
            yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and TOKEN_HEX.fullmatch(key):
                yield key
            yield from _seeded_tokens(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _seeded_tokens(item)


def seeded_token_hashes(client):
    """Return hashes of UUID-shaped values already present after corpus seeding."""
    tokens = set()
    for collection in client.collections():
        for path, document in _documents(collection):
            tokens.update(part for part in path.split('/') if TOKEN_HEX.fullmatch(part))
            tokens.update(_seeded_tokens(document))
    return sorted(sha256(value.encode('ascii')).hexdigest() for value in tokens)


def _same_snapshot_value(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_snapshot_value(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_same_snapshot_value(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def _preserved_fields(before, after, prefix=''):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return
    for field in sorted(before.keys() & after.keys()):
        # Timestamp rules address nested fields with slash-separated paths.
        if '/' in field:
            continue
        path = prefix + field
        if _same_snapshot_value(before[field], after[field]):
            yield path
        yield from _preserved_fields(before[field], after[field], path + '/')


def _documents(collection):
    # list_documents also returns missing parents that own populated subcollections.
    for ref in collection.list_documents():
        snapshot = ref.get()
        if snapshot.exists:
            yield ref.path, snapshot.to_dict()
        for child in ref.collections():
            yield from _documents(child)


def _episode_attach_memo_failure_reason(
    uid, cid, conversation, derived_documents, *, transcript_decoder=None, content_key_fn=None, load_bindings=None
):
    """Return a value-free failure code when this side's attach memo check fails."""
    try:
        if load_bindings is not None:
            bindings = load_bindings()
            transcript_decoder = bindings.decode_transcript_segments_verified
            content_key_fn = bindings.content_key
        link_path = f'users/{uid}/episode_links/{cid}'
        link = derived_documents.get(link_path)
        if not isinstance(link, dict):
            return 'missing_link'
        raw_segments = conversation.get('transcript_segments')
        if raw_segments is None:
            return 'missing_transcript'
        row = dict(conversation)
        if isinstance(raw_segments, (list, tuple)):
            # Go observations contain the already-decoded segment list.
            row['transcript_segments'] = raw_segments
        else:
            try:
                row['transcript_segments'] = transcript_decoder(
                    uid, raw_segments, bool(conversation.get('transcript_segments_compressed'))
                )
            except Exception:
                return 'transcript_decode_failed'
        key = content_key_fn(row)
        if not key:
            return 'content_key_unavailable'
        completed = link.get('attach_completed')
        if completed != key:
            return 'completed_key_mismatch'
        if link.get('attach_revision') != key:
            return 'revision_key_mismatch'
        if link.get('attach_owner_id') != link.get('episode_id'):
            return 'owner_binding_mismatch'
        if link.get('attach_finalized') is not None and link.get('attach_finalized') != completed:
            return 'finalized_binding_mismatch'
        return ''
    except Exception:
        return 'check_failed'


def episode_attach_memo_valid(
    uid, cid, conversation, derived_documents, *, transcript_decoder=None, content_key_fn=None
):
    """Return value-free evidence that this side's attach memo matches its transcript."""
    return not _episode_attach_memo_failure_reason(
        uid,
        cid,
        conversation,
        derived_documents,
        transcript_decoder=transcript_decoder,
        content_key_fn=content_key_fn,
    )


def episode_attach_memo_failure_reason(
    uid, cid, conversation, derived_documents, *, transcript_decoder=None, content_key_fn=None
):
    return _episode_attach_memo_failure_reason(
        uid,
        cid,
        conversation,
        derived_documents,
        transcript_decoder=transcript_decoder,
        content_key_fn=content_key_fn,
    )


def ordinary_sync_attach_memo_failure_reason(uid, cid, conversation, documents, *, key_fn, python_keys=None):
    """Verify final Go memo binding or the proven Python skip-cache fallthrough."""
    final_key = key_fn(uid, conversation)
    link = documents.get(f'users/{uid}/episode_links/{cid}')
    if link is None and python_keys is not None:
        return ''
    if not isinstance(link, dict):
        return 'missing_link'

    revision, completed, finalized = (link.get(f'attach_{name}') for name in ('revision', 'completed', 'finalized'))
    owner = link.get('attach_owner_id')
    if python_keys is not None and all(value is None for value in (revision, completed, finalized, owner)):
        return ''
    if not owner or owner != link.get('episode_id') or owner != conversation.get('episode_id'):
        return 'owner_binding_mismatch'
    if python_keys is not None:
        if not isinstance(revision, str) or not revision or revision != completed or revision not in python_keys:
            return 'completed_key_mismatch'
        if finalized is not None and finalized != revision:
            return 'finalized_binding_mismatch'
        return ''
    if not final_key or revision != final_key or completed != final_key:
        return 'completed_key_mismatch'
    if finalized != final_key:
        return 'finalized_binding_mismatch'
    return ''


class CaseState:
    def __init__(self, client, case):
        self.client = client
        self.case = case
        self.uid = case.get('uid', f'replay-{case["name"]}')
        self.cid = case.get('conversation_id', case['name'])
        self.home_dirty_receipt_path = f'users/{self.uid}/episode_links/{self.cid}'
        self.batch_privacy_document_path = f'batch_pipeline_privacy/{sha256(self.uid.encode("utf-8")).hexdigest()}'
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
        self.replay_side = None
        self.episode_attach_memo_writer_keys = []
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
            'batch_pipeline_privacy_document_reads': 0,
            'batch_pipeline_privacy_document_writes': 0,
            'batch_pipeline_privacy_document_deletes': 0,
        }
        self.go_evidence = {}
        self._metrics_lock = Lock()
        self.cost_measured = False
        self.profile_writes = []
        self.task_writes = []
        self.task_embedding_inputs = {}
        self.started_at = None
        self.seeded_token_hashes = []
        self.batch_privacy_seed = None
        self.home_dirty_receipt_trace = {'set_true': 0, 'set_false': 0, 'deleted': 0, 'other_write': 0}

    def record_provider_call(self, feature, prompt, completion):
        prompt_tokens = prompt_token_estimate(prompt)
        completion_tokens = token_estimate(completion)
        with self._metrics_lock:
            self.provider_calls.append(feature)
            self.llm_tokens['prompt'] += prompt_tokens
            self.llm_tokens['completion'] += completion_tokens
        return prompt_tokens, completion_tokens

    def record_embedding_request(self, values):
        if not isinstance(values, list):
            values = [values]
        with self._metrics_lock:
            self.provider_calls.append('openai-embeddings')
            self.embedding_tokens += sum(embedding_token_estimate(value) for value in values)

    def add_firestore_operations(self, **counts):
        with self._metrics_lock:
            for name, count in counts.items():
                self.firestore_operations[name] += count

    def record_home_dirty_receipt_write(self, value):
        bucket = (
            'deleted'
            if value == 'deleted'
            else 'set_true' if value is True else 'set_false' if value is False else 'other_write'
        )
        with self._metrics_lock:
            self.home_dirty_receipt_trace[bucket] += 1

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
        self.initial_conversation = self.conversation.get().to_dict() or {}
        self.initial_updated_at = self.initial_conversation.get('updated_at')
        self.batch_privacy_seed = self.batch_privacy_snapshot()
        self.started_at = datetime.now(timezone.utc)

    def batch_privacy_snapshot(self):
        collection, document = self.batch_privacy_document_path.split('/')
        snapshot = self.client.collection(collection).document(document).get()
        return {'exists': snapshot.exists, 'fields': pack(snapshot.to_dict() or {})}

    def observe(self, status, before, *, load_memo_bindings=None):
        after = self.documents()
        changed_documents = {
            path: after.get(path)
            for path in sorted(before.keys() | after.keys())
            if not _same_snapshot_value(before.get(path), after.get(path))
        }
        if getattr(self, 'compare_full_derived_documents', False):
            user_path = f'users/{self.uid}'
            full_case_paths = {
                path
                for path in after
                if path == user_path or path.startswith(user_path + '/') or path == self.batch_privacy_document_path
            }
            derived_documents = {path: after.get(path) for path in sorted(full_case_paths | changed_documents.keys())}
        else:
            derived_documents = changed_documents
        document = self.conversation.get().to_dict()
        preserved_fields = {
            path: fields
            for path, row in derived_documents.items()
            if (fields := list(_preserved_fields(before.get(path), row)))
        }
        preserved_fields[''] = list(_preserved_fields(pack(getattr(self, 'initial_conversation', {})), pack(document)))
        memo_expected = False
        side = getattr(self, 'replay_side', None)
        if side in {'python', 'go'}:
            memo_bindings = load_memo_bindings()
            stored = document or {}
            memo_failure_reason = ordinary_sync_attach_memo_failure_reason(
                self.uid,
                self.cid,
                stored,
                derived_documents,
                python_keys=self.episode_attach_memo_writer_keys if side == 'python' else None,
                key_fn=memo_bindings.current_key,
            )
            if side == 'go':
                link = derived_documents.get(self.home_dirty_receipt_path) or {}
                memo_expected = bool(
                    link.get('attach_finalized') is not None
                    or (
                        status == 'completed'
                        and stored.get('episode_id')
                        and stored.get('summary_output_present') is True
                        and memo_bindings.memo_eligible(stored)
                    )
                )
        else:
            memo_failure_reason = _episode_attach_memo_failure_reason(
                getattr(self, 'uid', ''),
                getattr(self, 'cid', ''),
                document or {},
                derived_documents,
                load_bindings=load_memo_bindings,
            )
        empty_privacy = {'exists': False, 'fields': {}}
        privacy_seed = getattr(self, 'batch_privacy_seed', None) or empty_privacy
        privacy_final = self.batch_privacy_snapshot() if hasattr(self, 'client') else empty_privacy
        observation = {
            'owner_id': getattr(self, 'uid', ''),
            'conversation_id': getattr(self, 'cid', ''),
            'seeded_token_hashes': getattr(self, 'seeded_token_hashes', []),
            'status': status,
            'queue_fanout_key': self.queue_fanout_key,
            'updated_at_changed': (document or {}).get('updated_at') != self.initial_updated_at,
            'preserved_fields': preserved_fields,
            'admitted': self.admitted,
            'episode_attach_memo_valid': not memo_failure_reason,
            'episode_attach_memo_expected': memo_expected,
            'episode_attach_memo_failure_reason': memo_failure_reason,
            'started_at': self.started_at.isoformat(),
            'finished_at': datetime.now(timezone.utc).isoformat(),
            'profile_writes': getattr(self, 'profile_writes', []),
            'task_writes': getattr(self, 'task_writes', []),
            'task_embedding_inputs': getattr(self, 'task_embedding_inputs', {}),
            'provider_calls': sorted(self.provider_calls),
            'cost': self.cost(),
            'go_evidence': self.go_evidence,
            'batch_pipeline_privacy': {
                'seed': privacy_seed,
                'final': privacy_final,
            },
            'home_dirty_receipt_trace': dict(
                getattr(
                    self, 'home_dirty_receipt_trace', {'set_true': 0, 'set_false': 0, 'deleted': 0, 'other_write': 0}
                )
            ),
            'effects': pack(self.effects),
            'conversation': pack(document),
            'derived_documents': derived_documents,
            'webhooks': sorted(self.webhooks, key=lambda delivery: delivery['app']),
        }
        operation_sources = getattr(self, 'firestore_operation_sources', None)
        if operation_sources:
            observation['firestore_operation_sources'] = operation_sources
        return observation

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
