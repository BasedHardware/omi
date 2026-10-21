"""Generation-pinned, owner-bound encrypted batch artifacts. No import-time IO.

Both standard and enhanced users get application encryption for temporary batch
artifacts. E2EE/unknown protection never enters the cloud worker. The required
policy callback checks current consent/deletion/migration and privacy generation;
callers must not substitute cached profile data for that transactional check.
"""

from dataclasses import dataclass
import hashlib
import json
import os
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud.storage.retry import DEFAULT_RETRY
from google.api_core.exceptions import NotFound

from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.source_audio import MAGIC as RECORD_MAGIC, materialize, read_reference
from utils.batch_pipeline.upload_policy import UPLOAD_CHUNK_BYTES, UPLOAD_TIMEOUT, UPLOAD_RETRY_SECONDS, UploadStream

AUDIO_LIMIT = 7200 * 32000 + 4096
RESULT_LIMIT = 8 * 1024 * 1024
MAGIC = b'OMIBP1'
# A one-hour PCM16 object is ~115 MB. Bound retransmission to 8 MiB chunks;
# allow slow links and transient service failures without changing object name.
UPLOAD_RETRY = DEFAULT_RETRY.with_deadline(UPLOAD_RETRY_SECONDS)


@dataclass(frozen=True)
class ProtectionContext:
    level: str
    generation: int

    def __post_init__(self) -> None:
        if self.level not in {'standard', 'enhanced'}:
            raise ValueError('cloud batch processing requires standard or enhanced protection')
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError('invalid privacy generation')


class ArtifactStore:
    def __init__(
        self,
        client: Any,
        *,
        bucket: str,
        namespace: str,
        authorize: Callable[[WorkItem], ProtectionContext],
        key_for_owner: Callable[[str], bytes],
        register_artifact: Callable[[WorkItem, str, str, ProtectionContext], None],
        shadow_result: Callable | None = None,
    ) -> None:
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]', bucket):
            raise ValueError('explicit staging bucket required')
        if not re.fullmatch(r'batch_pipeline_(prod|dev|test_[a-z0-9_]{1,40})', namespace):
            raise ValueError('explicit stage-qualified artifact namespace required')
        self.client = client
        self.bucket = client.bucket(bucket)
        self.bucket_name = bucket
        self.namespace = namespace
        self.authorize = authorize
        self.key_for_owner = key_for_owner
        self.register_artifact = register_artifact
        self.shadow_result = shadow_result

    def owner_prefix(self, owner_id: str) -> str:
        return f'batch-pipeline/{self.namespace}/owners/{hashlib.sha256(owner_id.encode()).hexdigest()}/'

    def _aad(self, item: WorkItem, kind: str, context: ProtectionContext) -> bytes:
        identity = {
            'version': 1,
            'namespace': self.namespace,
            'owner_id': item.owner_id,
            'segment_id': item.segment_id,
            'capture_at': item.capture_at,
            'duration_seconds': item.duration_seconds,
            'unit_kind': item.unit_kind,
            'conversation_id': item.conversation_id,
            'kind': kind,
            'protection': context.level,
            'privacy_generation': context.generation,
            'audio_uri': item.audio_uri if kind == 'results' else '',
        }
        if item.shadow:
            identity['shadow'] = True
        return json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()

    def _unchanged(self, item: WorkItem, context: ProtectionContext) -> None:
        if self.authorize(item) != context:
            raise PermissionError('batch artifact policy changed during IO')

    def _seal(self, item: WorkItem, kind: str, context: ProtectionContext, body: bytes) -> bytes:
        nonce = os.urandom(12)
        key = self.key_for_owner(item.owner_id)
        if len(key) != 32:
            raise ValueError('batch artifacts require a 256-bit owner key')
        return MAGIC + nonce + AESGCM(key).encrypt(nonce, body, self._aad(item, kind, context))

    def _write(self, item: WorkItem, kind: str, body: bytes, limit: int, *, result_key: str | None = None) -> str:
        if not body or len(body) > limit:
            raise ValueError('batch artifact exceeds bounded payload size')
        context = self.authorize(item)
        if item.privacy_generation is None or context.generation != item.privacy_generation:
            raise PermissionError('batch artifacts require the admitted privacy generation')
        key = result_key or uuid4().hex
        if not re.fullmatch(r'[0-9a-f]{32}', key):
            raise ValueError('bounded artifact identity required')
        name = f'{self.owner_prefix(item.owner_id)}{kind}/{item.segment_id}/{key}.enc'
        # Durable deletion outbox precedes cloud IO, including uncertain uploads.
        # Reserved random names are create-only and are never reused. The outbox
        # may erase this unique name before the provider returns its generation.
        registered_at = time.monotonic()
        self.register_artifact(item, f'gs://{self.bucket_name}/{name}', kind, context)
        self._unchanged(item, context)
        if time.monotonic() - registered_at > 30:
            raise TimeoutError('artifact registration too old to begin upload')
        blob = self.bucket.blob(name)
        blob.chunk_size = UPLOAD_CHUNK_BYTES
        # Omitting size forces the SDK's resumable path even for short captures.
        # SDK retries reuse this stream/session and the one registered name.
        blob.upload_from_file(
            UploadStream(self._seal(item, kind, context, body)),
            content_type='application/octet-stream',
            if_generation_match=0,
            timeout=UPLOAD_TIMEOUT,
            retry=UPLOAD_RETRY,
        )
        # An upload may succeed while deletion races it. Never return its URI
        # after revocation. Delete that exact version, never a newer object.
        generation = int(blob.generation)
        try:
            self._unchanged(item, context)
        except Exception:
            blob.delete(if_generation_match=generation, timeout=30, retry=None)
            raise
        if generation <= 0:
            raise ValueError('storage did not return an immutable generation')
        return f'gs://{self.bucket_name}/{name}#{generation}'

    def _read(self, item: WorkItem, uri: str, kind: str, limit: int) -> bytes:
        context = self.authorize(item)
        if item.privacy_generation is None or context.generation != item.privacy_generation:
            raise PermissionError('batch artifacts require the admitted privacy generation')
        parsed = urlsplit(uri)
        prefix = f'{self.owner_prefix(item.owner_id)}{kind}/{item.segment_id}/'
        name = parsed.path.removeprefix('/')
        if (
            parsed.scheme != 'gs'
            or parsed.netloc != self.bucket_name
            or parsed.query
            or not name.startswith(prefix)
            or not re.fullmatch(r'[0-9a-f]{32}\.enc', name[len(prefix) :])
            or not re.fullmatch(r'[1-9][0-9]{0,19}', parsed.fragment)
        ):
            raise ValueError('artifact must be an owner/segment-bound generation-pinned staging reference')
        generation = int(parsed.fragment)
        blob = self.bucket.blob(name, generation=generation)
        blob.reload(if_generation_match=generation, timeout=30, retry=None)
        if not blob.size or not 0 < blob.size <= limit + len(MAGIC) + 28:
            raise ValueError('stored batch artifact exceeds bounded payload size')
        sealed = blob.download_as_bytes(if_generation_match=generation, timeout=60, retry=None)
        if len(sealed) > limit + len(MAGIC) + 28 or not sealed.startswith(MAGIC):
            raise ValueError('invalid batch artifact envelope')
        offset = len(MAGIC)
        body = AESGCM(self.key_for_owner(item.owner_id)).decrypt(
            sealed[offset : offset + 12], sealed[offset + 12 :], self._aad(item, kind, context)
        )
        self._unchanged(item, context)
        return body

    def stage_audio(self, item: WorkItem, wav: bytes) -> str:
        """Admission calls this before enqueue; audio AAD excludes its own URI."""
        return self._write(item, 'audio', wav, AUDIO_LIMIT)

    def fetch_audio(self, item: WorkItem) -> bytes:
        body = self._read(item, item.audio_uri, 'audio', AUDIO_LIMIT)
        if body.startswith(RECORD_MAGIC):
            conversation_id = item.conversation_id
            if not conversation_id:
                raise ValueError('retained audio requires a registered conversation')
            allowed = {
                os.getenv('BUCKET_PRIVATE_CLOUD_SYNC', 'omi-private-cloud-sync'),
                os.getenv('BUCKET_AUDIO_DERIVED', '').strip(),
            }
            wav = materialize(
                body,
                item,
                lambda ref: read_reference(
                    self.client, ref, item.owner_id, conversation_id, allowed, self.key_for_owner(item.owner_id)
                ),
            )
            self.authorize(item)
            return wav
        return body

    def persist_result(self, item: WorkItem, payload: dict[str, Any]) -> str:
        if item.shadow:
            # Shadow transcripts/diarization never enter durable storage.
            if self.shadow_result is None:
                raise PermissionError('shadow result sink required')
            self.authorize(item)
            self.shadow_result(item, payload)
            return 'shadow:' + item.segment_id
        body = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
        return self._write(item, 'results', body, RESULT_LIMIT)

    def persist_recovery_result(self, item: WorkItem, payload: dict[str, Any], token: str) -> str:
        if item.shadow:
            raise PermissionError('shadow recovery may only record outcomes')
        body = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
        return self._write(item, 'results', body, RESULT_LIMIT, result_key=token)

    def find_recovery_result(self, item: WorkItem, token: str) -> str | None:
        if not re.fullmatch(r'[0-9a-f]{32}', token):
            raise ValueError('bounded recovery token required')
        context = self.authorize(item)
        if context.generation != item.privacy_generation:
            raise PermissionError('recovery generation changed')
        name = f'{self.owner_prefix(item.owner_id)}results/{item.segment_id}/{token}.enc'
        blob = self.bucket.blob(name)
        try:
            blob.reload(timeout=30, retry=None)
        except NotFound:
            return None
        uri = f'gs://{self.bucket_name}/{name}#{int(blob.generation)}'
        # Authenticate the owner, admitted clocks, generation and encrypted body
        # before acknowledging an upload whose successful reply was lost.
        self.load_result(item, uri)
        return uri

    def load_result(self, item: WorkItem, uri: str) -> dict[str, Any]:
        payload = json.loads(self._read(item, uri, 'results', RESULT_LIMIT))
        if not isinstance(payload, dict):
            raise ValueError('batch result must be a JSON object')
        return payload
