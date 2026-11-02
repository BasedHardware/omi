"""Conversation snapshots, separate from immutable per-window custody receipts.

An open writer invalidates the snapshot before accepting new frames. A crash
leaves that marker open and readers list prefixes. Part ACKs never await seal.
"""

import hashlib
import json

from google.api_core.exceptions import NotFound, PreconditionFailed

from utils import encryption
from utils.other.audio_frame_table import entries, validate_frames
from utils.observability.fallback import record_fallback

SCHEMA = 'audio_conversation_seal_v1'
MAX_INDEX_BYTES = 16 * 1024 * 1024
PART_BYTES = 16 * 1024 * 1024


def index_path(uid: str, conversation_id: str) -> str:
    if any(not value or '/' in value or value in {'.', '..'} for value in (uid, conversation_id)):
        raise ValueError('invalid seal owner')
    return f'audio-outbox/{uid}/{conversation_id}/seal.json'


def _encode(value: dict) -> bytes:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError('seal index exceeds bound')
    return raw


def _read(bucket, uid: str, path: str):
    blob = bucket.blob(path)
    # SDK's single-shot GET stamps blob.generation from X-goog-generation.
    # No range retry may splice generations while versioning is disabled.
    raw = blob.download_as_bytes(single_shot_download=True, timeout=10, retry=None)
    if not blob.generation or len(raw) > MAX_INDEX_BYTES:
        raise ValueError('seal GET has no generation or exceeds bound')
    if len(raw) < 41 or raw[:8] != b'OMISEAL1' or raw[8:9] not in (b'E', b'P'):
        raise ValueError('seal GET envelope invalid')
    digest, payload = raw[9:41], raw[41:]
    if raw[8:9] == b'E':
        payload = encryption.decrypt_audio_file(payload, uid)
    if hashlib.sha256(payload).digest() != digest:
        raise ValueError('seal GET checksum mismatch')
    return json.loads(payload), int(blob.generation)


class ConversationSealIndex:
    def __init__(self, bucket, uid: str, source: str, protection: str, write_gate, baseline, allowed=lambda conv: True):
        self.bucket, self.uid, self.source = bucket, uid, source
        self.protection, self.write_gate, self.baseline = protection, write_gate, baseline
        self.active: dict[str, dict] = {}
        self.failed: set[str] = set()
        self.versioning_checked = False
        self.allowed = allowed

    def _put(self, path, value, generation):
        conversation_id = path.split('/')[2]
        if not self.allowed(conversation_id):
            raise ValueError('seal refused by conversation deletion intent')
        raw = _encode(value)
        encrypted = self.protection == 'enhanced'
        blob = self.bucket.blob(path)
        blob.metadata = {'sha256': hashlib.sha256(raw).hexdigest(), 'encrypted': str(encrypted).lower()}
        body = encryption.encrypt_audio_chunk(raw, self.uid) if encrypted else raw
        data = b'OMISEAL1' + (b'E' if encrypted else b'P') + hashlib.sha256(raw).digest() + body
        blob.upload_from_string(
            data, if_generation_match=generation, timeout=10, retry=None, content_type='application/octet-stream'
        )
        if not self.allowed(conversation_id):
            blob.delete(if_generation_match=int(blob.generation), timeout=10, retry=None)
            raise ValueError('seal deleted during publication')

    def _update(self, conversation_id, mutate):
        path = index_path(self.uid, conversation_id)
        with self.write_gate(self.uid, self.bucket):
            for attempt in range(3):
                try:
                    current, generation = _read(self.bucket, self.uid, path)
                    if current['schema'] != SCHEMA or current['conversation_id'] != conversation_id:
                        raise ValueError('seal identity mismatch')
                except NotFound:
                    generation = 0
                    current = {
                        'schema': SCHEMA,
                        'conversation_id': conversation_id,
                        'writers': {},
                        'parts': {},
                        'baseline': self.baseline(conversation_id),
                    }
                mutate(current)
                current['state'] = (
                    'sealed'
                    if current['writers'] and all(state == 'closed' for state in current['writers'].values())
                    else 'open'
                )
                try:
                    if generation and not self.versioning_checked:
                        self.bucket.reload(timeout=10, retry=None)
                        # CAS + a single-shot GET work with versioning off. Do
                        # not rely on an old generation surviving replacement.
                        self.versioning_checked = True
                    self._put(path, current, generation)
                    return
                except PreconditionFailed:
                    if attempt == 2:
                        raise

    def begin(self, conversation_id: str):
        if conversation_id in self.active:
            return
        if len(self.active) >= 128:
            raise ValueError('seal active conversation bound reached')
        next_part = 0

        def begin(root):
            nonlocal next_part
            next_part = 1 + max(
                (part['part'] for part in root['parts'].values() if part['source'] == self.source), default=-1
            )
            root['writers'][self.source] = 'open'

        self._update(conversation_id, begin)
        self.active[conversation_id] = {'part': next_part, 'bytes': 0, 'receipts': []}

    def add(self, receipt: dict, frames: list[dict]):
        conversation_id = receipt['conversation_id']
        if conversation_id not in self.active:
            raise ValueError('seal writer was not opened')
        validate_frames(frames, int(receipt['sample_rate']))
        part = self.active[conversation_id]
        if part['receipts'] and part['bytes'] + receipt['samples'] * 2 > PART_BYTES:
            self.seal(conversation_id, close=False)
            part = self.active[conversation_id]
        part['receipts'].append({'receipt': receipt, 'frames': frames, 'projections': []})
        part['bytes'] += receipt['samples'] * 2
        if part['bytes'] >= PART_BYTES:
            self.seal(conversation_id, close=False)

    def project(self, receipt: dict, paths: list[str]):
        part = self.active.get(receipt['conversation_id'])
        if part:
            for item in part['receipts']:
                if item['receipt']['manifest_path'] == receipt['manifest_path']:
                    item['projections'] = paths

    def seal(self, conversation_id: str, *, close: bool = True):
        if conversation_id in self.failed:
            return
        part = self.active.get(conversation_id)
        if part is None:
            return
        key = f'{self.source}/{part["part"]}'
        value = {'source': self.source, 'part': part['part'], 'receipts': part['receipts']}
        # Immutable bounded part object, with a deterministic conversation/part name.
        if part['receipts']:
            path = f'audio-outbox/{self.uid}/{conversation_id}/seals/{key}.json'
            with self.write_gate(self.uid, self.bucket):
                try:
                    self._put(path, value, 0)
                except PreconditionFailed:
                    existing, _ = _read(self.bucket, self.uid, path)
                    if existing != value:
                        raise ValueError('seal part identity conflict')

        def publish(root):
            if part['receipts']:
                root['parts'][key] = value
            if close:
                root['writers'][self.source] = 'closed'

        self._update(conversation_id, publish)
        if close:
            self.active.pop(conversation_id)
        else:
            self.active[conversation_id] = {'part': part['part'] + 1, 'bytes': 0, 'receipts': []}

    def try_add(self, receipt: dict, frames: list[dict]):
        try:
            self.add(receipt, frames)
        except Exception:
            self.failed.add(receipt['conversation_id'])
            record_fallback(
                component='pusher',
                from_mode='raw_audio',
                to_mode='private_cloud_sync',
                reason='other',
                outcome='degraded',
            )

    def try_seal(self, conversation_id: str):
        try:
            self.seal(conversation_id)
        except Exception:
            self.failed.add(conversation_id)
            record_fallback(
                component='pusher',
                from_mode='raw_audio',
                to_mode='private_cloud_sync',
                reason='other',
                outcome='degraded',
            )


def create_seal_index(storage, uid: str, source: str, protection=None):
    return ConversationSealIndex(
        storage.get_private_cloud_sync_bucket(),
        uid,
        source,
        protection or storage.users_db.get_data_protection_level(uid),
        storage.owner_storage_write_gate,
        lambda conversation_id: storage.list_audio_chunks(
            uid, conversation_id, source_identity=True, require_archive=True
        ),
        lambda conversation_id: not storage.conversation_tombstones.is_deleted(uid, conversation_id),
    )


def sealed_entries(bucket, uid: str, conversation_id: str) -> list[dict]:
    root, _ = _read(bucket, uid, index_path(uid, conversation_id))
    if root['schema'] != SCHEMA or root['conversation_id'] != conversation_id or root['state'] != 'sealed':
        raise ValueError('conversation seal is absent or open')
    if not root['writers'] or any(state != 'closed' for state in root['writers'].values()):
        raise ValueError('conversation seal has open writers')
    result = list(root['baseline'])
    for part in root['parts'].values():
        for item in part['receipts']:
            receipt = item['receipt']
            if receipt['conversation_id'] != conversation_id or receipt['bucket'] != bucket.name:
                raise ValueError('seal part owner mismatch')
            if not receipt['path'].startswith(f'raw-live/{uid}/{conversation_id}/') or not receipt[
                'manifest_path'
            ].startswith(f'audio-outbox/{uid}/{conversation_id}/'):
                raise ValueError('seal part path mismatch')
            if not all(receipt[key] for key in ('generation', 'manifest_generation', 'sha256', 'manifest_sha256')):
                raise ValueError('seal part lacks custody proof')
            if validate_frames(item['frames'], receipt['sample_rate']) != receipt['samples']:
                raise ValueError('seal part samples mismatch')
            result.extend(
                entries(
                    item['frames'],
                    receipt['sample_rate'],
                    {
                        'path': receipt['path'],
                        'generation': int(receipt['generation']),
                        'size': None,
                        'pcm_sha256': receipt['pcm_sha256'],
                    },
                )
            )
    return sorted(result, key=lambda entry: entry['timestamp'])
