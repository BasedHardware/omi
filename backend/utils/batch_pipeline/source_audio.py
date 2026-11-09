"""Authenticated reference manifests over retained audio; never copies canonical audio.

Pure decoding shared by the CPU admission coordinator and the GPU artifact reader.
Every source is owner/conversation scoped and pinned to a GCS generation. The
batch retention outbox owns only the small manifest, never the retained source.
"""

import audioop
import hashlib
import json
import struct
from typing import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.batch_pipeline.audio import audio_unit, with_context
from utils.batch_pipeline import leaf_timings
from utils.other.raw_audio import decode_capture

MAGIC = b'OMIRECORD1\n'
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_REFERENCES = 4096


def batch_timing_store(references: list[dict]) -> str | None:
    """Only homogeneous live PCM custody references prove the batch clock."""
    if references and all(str(ref.get('path') or '').endswith(('.batch.enc', '.batch.bin')) for ref in references):
        return 'batch'
    return None


class RetainedAudioInvalid(ValueError):
    """Retained audio that can never decode from these stored bytes.

    Deterministic on the pinned object generations: a retry re-reads the
    same bytes and fails the same way, so the failure must end the GPU
    chain and recovery lane instead of walking the bounded retry ladder.
    """


class InvalidRetainedManifest(RetainedAudioInvalid):
    """The stored manifest itself can never materialize; a retry reads the same bytes."""


class RetainedAudioOutsideAdmittedSource(ValueError):
    """A retained manifest names a source this deployment does not admit.

    Deliberately NOT a ``RetainedAudioInvalid`` subclass: the bytes may be
    perfectly sound — the *deploy's* admitted bucket set is what rejects
    them, and a later deploy can admit them, so the bounded retry ladder
    keeps walking. It is typed anyway so the fetch_decode boundary never has
    to guess: the worker evidence, the per-attempt failure record and the
    terminal quarantine all name ``outside_admitted_source`` instead of
    collapsing the whole cohort into ``unclassified`` ValueErrors (the
    x386/30m production signature family that could not be told apart from
    any other bare fault).

    Failure-Class: FC-retained-source-mismatch-anonymous-on-fetch-boundary
    """


def decode_source(raw: bytes, ref: dict, owner_key: bytes) -> bytes:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise RetainedAudioInvalid('invalid retained audio size')
    metadata = ref.get('metadata') or {}
    path = ref['path']
    encrypted = path.endswith('.enc') or metadata.get('encrypted') == 'true'
    if encrypted:
        decoded, offset = bytearray(), 0
        aes = AESGCM(owner_key)
        with leaf_timings.measure('decrypt'):
            while offset < len(raw):
                if offset + 4 > len(raw):
                    raise RetainedAudioInvalid('truncated encrypted audio length')
                size = struct.unpack_from('>I', raw, offset)[0]
                offset += 4
                if not 28 <= size <= MAX_SOURCE_BYTES or offset + size > len(raw):
                    raise RetainedAudioInvalid('invalid encrypted audio frame')
                try:
                    decoded.extend(aes.decrypt(raw[offset : offset + 12], raw[offset + 12 : offset + size], None))
                except InvalidTag:
                    raise RetainedAudioInvalid('retained audio authentication failed') from None
                offset += size
        raw = bytes(decoded)
    if path.startswith('raw-live/'):
        if hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
            raise RetainedAudioInvalid('retained capture checksum mismatch')
        try:
            return leaf_timings.call('decode', decode_capture, raw, metadata, 16000)
        except ValueError as error:
            raise RetainedAudioInvalid(str(error)) from error
    if '.opus' in path:
        # Existing legacy chunk codec, shared with playback. Import is lazy in
        # the codec binding; no storage/database/provider SDK is constructed.
        from utils.other.audio_opus import decode_opus_to_pcm

        try:
            return leaf_timings.call('decode', decode_opus_to_pcm, raw, sample_rate=16000)
        except ValueError as error:
            raise RetainedAudioInvalid(str(error)) from error
    rate = ref.get('sample_rate', 16000)
    try:
        rate = int(rate)
    except (TypeError, ValueError, OverflowError):
        # A stored rate that was never an integer is deterministic on the
        # pinned manifest: every retry re-reads the same metadata and fails
        # the same conversion, so the fault must end the GPU chain with the
        # family token instead of walking the bounded retry ladder on
        # identical bytes and booking the unit as an anonymous production
        # error (the sensor's bare ValueError cohort at fetch_decode). The
        # raise site carries the type and the worker boundary reads the
        # type — never an exception message.
        raise RetainedAudioInvalid('invalid retained PCM') from None
    if len(raw) % 2 or not 8000 <= rate <= 48000:
        raise RetainedAudioInvalid('invalid retained PCM')
    return leaf_timings.call('decode', audioop.ratecv, raw, 2, 1, rate, 16000, None)[0] if rate != 16000 else raw


def validate_reference(ref: dict, uid: str, conversation_id: str, allowed_buckets: set[str]) -> None:
    bucket = ref.get('bucket')
    # A non-string bucket is never admitted — and must not raise TypeError on
    # the set membership probe (unhashable dict/list shapes), which would
    # surface as one more anonymous fault class at the fetch_decode boundary.
    if not isinstance(bucket, str) or bucket not in allowed_buckets:
        # The allowed set is deploy configuration, not the manifest: stay
        # retryable — but typed, so the fetch_decode boundary names the fault
        # instead of collapsing it into the anonymous ValueError bucket.
        raise RetainedAudioOutsideAdmittedSource('retained audio reference is outside admitted source')
    path = ref.get('path', '')
    # Generations arrive as JSON numbers or zero-padded strings; both were
    # accepted by the former str().isdigit() guard. isdigit() also accepts
    # unicode digits ('²') that int() then rejects with a bare ValueError
    # past this validator, so the string arm admits ASCII digits only.
    generation = ref.get('generation')
    generation_ok = isinstance(generation, int) and not isinstance(generation, bool) and generation > 0
    if not generation_ok and isinstance(generation, str):
        generation_ok = bool(generation) and all(char in '0123456789' for char in generation) and int(generation) > 0
    if (
        not isinstance(path, str)
        or not path.startswith((f'chunks/{uid}/{conversation_id}/', f'raw-live/{uid}/{conversation_id}/'))
        or any(part in {'.', '..'} for part in path.split('/'))
        or not generation_ok
    ):
        raise InvalidRetainedManifest('retained audio reference is outside admitted source')


def read_reference(
    client,
    ref: dict,
    uid: str,
    conversation_id: str,
    allowed_buckets: set[str],
    key: bytes,
    *,
    source_metadata=False,
    read_budget=None,
) -> bytes:
    validate_reference(ref, uid, conversation_id, allowed_buckets)
    generation = int(ref['generation'])
    blob = client.bucket(ref['bucket']).blob(ref['path'], generation=generation)
    if read_budget is not None:
        read_budget.begin()
    leaf_timings.call(
        'download_metadata',
        blob.reload,
        if_generation_match=generation,
        timeout=read_budget.timeout(30) if read_budget is not None else 30,
        retry=None,
    )
    if source_metadata:
        # Admission needs the source metadata in the manifest, including the
        # legacy sample rate. Reuse this generation-pinned GET, not a second one.
        ref['metadata'] = blob.metadata or {}
        if 'sample_rate' not in ref:
            ref['sample_rate'] = int(ref['metadata'].get('record_sample_rate', 16000))
    if not blob.size or not 0 < blob.size <= MAX_SOURCE_BYTES:
        raise RetainedAudioInvalid('retained audio source exceeds size budget')
    if read_budget is not None:
        read_budget.reserve(blob.size)
    raw = leaf_timings.call(
        'download',
        blob.download_as_bytes,
        if_generation_match=generation,
        timeout=read_budget.timeout(60) if read_budget is not None else 60,
        retry=None,
    )
    if read_budget is not None:
        read_budget.timeout(60)
    return decode_source(raw, ref, key)


def _well_formed(ref: dict) -> bool:
    return isinstance(ref.get('pcm_sha256'), str) and isinstance(ref.get('path', ''), str)


def materialize(body: bytes, item, fetch: Callable[[dict], bytes]) -> bytes:
    try:
        manifest = json.loads(body[len(MAGIC) :])
    except ValueError:
        raise InvalidRetainedManifest('retained audio manifest is not JSON') from None
    references = manifest.get('references') if isinstance(manifest, dict) else None
    if (
        not isinstance(references, list)
        or not isinstance(manifest.get('context'), dict)
        or not all(isinstance(ref, dict) and _well_formed(ref) for ref in references)
    ):
        raise InvalidRetainedManifest('malformed retained audio manifest')
    if (
        manifest.get('owner_id') != item.owner_id
        or manifest.get('conversation_id') != item.conversation_id
        or manifest.get('capture_at') != item.capture_at
        or not 1 <= len(references) <= MAX_REFERENCES
    ):
        raise InvalidRetainedManifest('retained audio manifest binding mismatch')
    pcm = bytearray(round(item.duration_seconds * 16000) * 2)
    previous = 0
    previous_key, previous_source = None, b''
    for ref in references:
        source_key = tuple(ref.get(name) for name in ('bucket', 'path', 'generation', 'pcm_sha256'))
        pinned = all(value is not None for value in source_key)
        if pinned and source_key == previous_key:
            source = previous_source
        else:
            source = fetch(ref)
            if hashlib.sha256(source).hexdigest() != ref['pcm_sha256']:
                raise RetainedAudioInvalid('retained PCM digest changed')
            previous_key, previous_source = source_key if pinned else None, source
        start, offset, frames = ref.get('start_frame'), ref.get('offset_frame'), ref.get('frames')
        if any(type(v) is not int for v in (start, offset, frames)) or start < previous or offset < 0 or frames <= 0:
            raise InvalidRetainedManifest('invalid retained audio slice')
        if (offset + frames) * 2 > len(source) or (start + frames) * 2 > len(pcm):
            raise InvalidRetainedManifest('retained audio slice exceeds capture')
        pcm[start * 2 : (start + frames) * 2] = source[offset * 2 : (offset + frames) * 2]
        previous = start + frames
    return with_context(audio_unit(item.capture_at, bytes(pcm)).wav, manifest['context'])
