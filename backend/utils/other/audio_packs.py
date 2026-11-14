"""Forward-only canonical capture archive. No legacy prefix is ever scanned.

GCS generations are the compare-and-swap authority. Callers serialize pack and
conversation rewrite with the account destructive-operation gate. Account wipes
already own that gate and sweep all three owner prefixes, including torn writes.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from typing import Any

from google.api_core.exceptions import NotFound, PreconditionFailed

RELEASE = '20261015-v1'
SOURCE_PREFIX = f'canonical-capture-{RELEASE}/'
PACK_PREFIX = f'canonical-packs-{RELEASE}/'
INDEX_PREFIX = f'canonical-pack-index-{RELEASE}/'
TARGET_BYTES = 256 * 1024 * 1024
MAX_CAPTURE_BYTES = 32 * 1024 * 1024


class CaptureDeleted(ValueError):
    pass


def owner_prefix(prefix: str, uid: str) -> str:
    if not uid or '/' in uid or uid in {'.', '..'}:
        raise ValueError('invalid archive owner')
    return f'{prefix}{uid}/'


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(bucket: Any, entry: dict[str, Any]) -> bytes:
    return bucket.blob(entry['source'], generation=int(entry['generation'])).download_as_bytes(
        if_generation_match=int(entry['generation'])
    )


def _tar(entries: list[dict[str, Any]], payloads: list[bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for entry, data in zip(entries, payloads, strict=True):
            entry['byte_offset'] = out.tell() + 512
            info = tarfile.TarInfo(entry['member'])
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo('manifest.json')
        data = _json(entries)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def verify_pack(data: bytes, manifest: dict[str, Any]) -> None:
    if _sha(data) != manifest['sha256']:
        raise ValueError('pack hash mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        expected = [e['member'] for e in manifest['entries']] + ['manifest.json']
        if archive.getnames() != expected:
            raise ValueError('pack members mismatch')
        for entry in manifest['entries']:
            member = archive.extractfile(entry['member'])
            info = archive.getmember(entry['member'])
            if info.offset_data != entry['byte_offset'] or info.size != entry['size']:
                raise ValueError('capture byte range mismatch')
            if member is None or _sha(member.read()) != entry['sha256']:
                raise ValueError('capture hash mismatch')
        member = archive.extractfile('manifest.json')
        if member is None or json.loads(member.read()) != manifest['entries']:
            raise ValueError('manifest round-trip mismatch')


def _delete_sources(bucket: Any, manifest: dict[str, Any]) -> None:
    for entry in manifest['entries']:
        try:
            bucket.blob(entry['source'], generation=int(entry['generation'])).delete(
                if_generation_match=int(entry['generation'])
            )
        except NotFound:
            pass


def _finish(bucket: Any, index: Any, manifest: dict[str, Any]) -> None:
    if manifest['state'] == 'complete':
        return
    if manifest['state'] == 'rewriting':
        _finish_rewrite(bucket, index, manifest)
        return
    pack = bucket.blob(manifest['pack'])
    if not pack.exists():
        data = _tar(manifest['entries'], [_read(bucket, entry) for entry in manifest['entries']])
        if _sha(data) != manifest['sha256']:
            raise ValueError('source changed while resuming pack')
        pack.upload_from_string(data, content_type='application/x-tar', if_generation_match=0)
    pack.reload()
    data = pack.download_as_bytes(if_generation_match=int(pack.generation))
    verify_pack(data, manifest)
    # Publish the verified generation before deleting a single source.
    if manifest['state'] == 'pending':
        manifest = {**manifest, 'state': 'verified', 'pack_generation': str(pack.generation)}
        index.upload_from_string(_json(manifest), if_generation_match=int(index.generation))
    elif str(pack.generation) != manifest['pack_generation']:
        raise ValueError('verified pack generation changed')
    _delete_sources(bucket, manifest)
    index.upload_from_string(_json({**manifest, 'state': 'complete'}), if_generation_match=int(index.generation))


def _validate_owner(manifest: dict[str, Any], uid: str) -> None:
    if manifest['owner'] != uid or not manifest['pack'].startswith(owner_prefix(PACK_PREFIX, uid)):
        raise ValueError('cross-owner pack')
    if any(not e['source'].startswith(owner_prefix(SOURCE_PREFIX, uid)) for e in manifest['entries']):
        raise ValueError('cross-owner capture')


def delete_conversation(bucket: Any, uid: str, conversation_id: str) -> None:
    """Caller holds account operation gate. Rewrites only affected new packs.

    An indivisible capture touching the requested range is erased in full.
    CAS rewrite at the same key avoids orphaning a replacement after a crash.
    Canonical buckets must have versioning and soft deletion disabled.
    """

    marker = bucket.blob(control_path(uid, 'deletions', conversation_id))
    try:
        marker.upload_from_string(_json({'owner': uid, 'conversation_id': conversation_id}), if_generation_match=0)
    except PreconditionFailed:
        pass

    def affected(entry: dict[str, Any]) -> bool:
        return any(
            conversation_id in conversation_chain(bucket, uid, r['conversation_id'])
            for r in entry['conversation_ranges']
            if r.get('conversation_id')
        )

    for index in bucket.list_blobs(prefix=owner_prefix(INDEX_PREFIX, uid)):
        relative = index.name.removeprefix(owner_prefix(INDEX_PREFIX, uid))
        if relative.split('/', 1)[0] in {'captures', 'deletions', 'links'}:
            continue
        manifest = json.loads(index.download_as_bytes(if_generation_match=int(index.generation)))
        _validate_owner(manifest, uid)
        # Pending intents are completed before a rewrite, including source cleanup.
        _finish(bucket, index, manifest)
        index.reload()
        manifest = json.loads(index.download_as_bytes(if_generation_match=int(index.generation)))
        if not any(affected(e) for e in manifest['entries']):
            continue
        pack = bucket.blob(manifest['pack'])
        pack.reload()
        old = pack.download_as_bytes(if_generation_match=int(pack.generation))
        # A durable rewrite intent includes the resulting hash and entries. On
        # retry either generation matches, and deletion can finish publication.
        keep = [e for e in manifest['entries'] if not affected(e)]
        with tarfile.open(fileobj=io.BytesIO(old), mode='r:') as archive:
            payloads: list[bytes] = []
            for entry in keep:
                member = archive.extractfile(entry['member'])
                if member is None:
                    raise ValueError('missing capture')
                payloads.append(member.read())
        data = _tar(keep, payloads)
        replacement = {
            **manifest,
            'entries': keep,
            'sha256': _sha(data),
            'state': 'rewriting',
            'previous_sha256': manifest['sha256'],
        }
        index.upload_from_string(_json(replacement), if_generation_match=int(index.generation))
        _finish_rewrite(bucket, index, replacement, data)
    for blob in bucket.list_blobs(prefix=owner_prefix(SOURCE_PREFIX, uid)):
        if affected(json.loads(blob.metadata['capture'])):
            blob.delete(if_generation_match=int(blob.generation))

    # Strongly consistent re-list while the caller still holds the owner gate.
    # Never acknowledge erasure when publication/cleanup left related bytes behind.
    for blob in bucket.list_blobs(prefix=owner_prefix(SOURCE_PREFIX, uid)):
        if affected(json.loads(blob.metadata['capture'])):
            raise RuntimeError('canonical erasure left an affected source')
    indexed_packs = {}
    for index in bucket.list_blobs(prefix=owner_prefix(INDEX_PREFIX, uid)):
        relative = index.name.removeprefix(owner_prefix(INDEX_PREFIX, uid))
        if relative.split('/', 1)[0] in {'captures', 'deletions', 'links'}:
            continue
        manifest = json.loads(index.download_as_bytes(if_generation_match=int(index.generation)))
        _validate_owner(manifest, uid)
        if manifest['state'] != 'complete' or any(affected(e) for e in manifest['entries']):
            raise RuntimeError('canonical erasure left an affected manifest')
        # Complete intents already verified this exact generation. Re-list metadata
        # instead of paying to retrieve every unaffected Coldline/Archive object.
        indexed_packs[manifest['pack']] = manifest['pack_generation']
    live_packs = {b.name: str(b.generation) for b in bucket.list_blobs(prefix=owner_prefix(PACK_PREFIX, uid))}
    if live_packs != indexed_packs:
        raise RuntimeError('canonical erasure found an unindexed pack or changed pack generation')


def _finish_rewrite(bucket: Any, index: Any, manifest: dict[str, Any], data: bytes | None = None) -> None:
    pack = bucket.blob(manifest['pack'])
    pack.reload()
    current = pack.download_as_bytes(if_generation_match=int(pack.generation))
    if _sha(current) == manifest['previous_sha256']:
        if data is None:
            with tarfile.open(fileobj=io.BytesIO(current), mode='r:') as archive:
                payloads: list[bytes] = []
                for entry in manifest['entries']:
                    member = archive.extractfile(entry['member'])
                    if member is None:
                        raise ValueError('missing rewrite member')
                    payloads.append(member.read())
            data = _tar(manifest['entries'], payloads)
        verify_pack(data, manifest)
        pack.storage_class = 'STANDARD'
        pack.upload_from_string(data, content_type='application/x-tar', if_generation_match=int(pack.generation))
        current = pack.download_as_bytes(if_generation_match=int(pack.generation))
    verify_pack(current, manifest)
    result = {**manifest, 'state': 'complete', 'pack_generation': str(pack.generation)}
    index.upload_from_string(_json(result), if_generation_match=int(index.generation))


def control_path(uid: str, kind: str, conversation_id: str) -> str:
    return f'{owner_prefix(INDEX_PREFIX, uid)}{kind}/{_sha(conversation_id.encode())}.json'


def conversation_chain(bucket: Any, uid: str, conversation_id: str) -> list[str]:
    chain: list[str] = []
    current = conversation_id
    while True:
        if current in chain:
            raise ValueError('canonical conversation link cycle')
        chain.append(current)
        link = bucket.get_blob(control_path(uid, 'links', current))
        if link is None:
            return chain
        row = json.loads(link.download_as_bytes(if_generation_match=int(link.generation)))
        if row['owner'] != uid or row['source'] != current:
            raise ValueError('canonical conversation link owner mismatch')
        current = row['target']


def assert_capture_allowed(bucket: Any, uid: str, ranges: list[dict[str, Any]]) -> None:
    for row in ranges:
        conversation_id = row.get('conversation_id')
        if conversation_id:
            for linked in conversation_chain(bucket, uid, conversation_id):
                if bucket.blob(control_path(uid, 'deletions', linked)).exists():
                    raise CaptureDeleted('canonical capture blocked by conversation deletion')


def link_conversations(bucket: Any, uid: str, sources: list[str], target: str) -> None:
    """Caller holds the account operation gate. Preserve bytes through manual merges."""
    assert_capture_allowed(bucket, uid, [{'conversation_id': target}])
    for source in sources:
        if source == target or source in conversation_chain(bucket, uid, target):
            raise ValueError('canonical merge would create a cycle')
        blob = bucket.get_blob(control_path(uid, 'links', source))
        if blob is not None:
            row = json.loads(blob.download_as_bytes(if_generation_match=int(blob.generation)))
            if row != {'owner': uid, 'source': source, 'target': target}:
                raise ValueError('canonical source already belongs to another merge')
            continue
        generation = 0
        blob = bucket.blob(control_path(uid, 'links', source))
        blob.upload_from_string(
            _json({'owner': uid, 'source': source, 'target': target}), if_generation_match=generation
        )

    # Resume even when the link was already published by an interrupted merge.
    # Rewrite the embedded manifest too, keeping every stored audio byte intact.
    for index in bucket.list_blobs(prefix=owner_prefix(INDEX_PREFIX, uid)):
        relative = index.name.removeprefix(owner_prefix(INDEX_PREFIX, uid))
        if relative.split('/', 1)[0] in {'captures', 'deletions', 'links'}:
            continue
        manifest = json.loads(index.download_as_bytes(if_generation_match=int(index.generation)))
        _validate_owner(manifest, uid)
        _finish(bucket, index, manifest)
        index.reload()
        manifest = json.loads(index.download_as_bytes(if_generation_match=int(index.generation)))
        entries = json.loads(_json(manifest['entries']))
        for entry in entries:
            entry['conversation_ranges'] = _retarget_ranges(bucket, uid, entry['conversation_ranges'])
        if entries == manifest['entries']:
            continue
        pack = bucket.blob(manifest['pack'])
        pack.reload()
        old = pack.download_as_bytes(if_generation_match=int(pack.generation))
        verify_pack(old, manifest)
        with tarfile.open(fileobj=io.BytesIO(old), mode='r:') as archive:
            payloads = []
            for entry in entries:
                member = archive.extractfile(entry['member'])
                if member is None:
                    raise ValueError('missing merge member')
                payloads.append(member.read())
        data = _tar(entries, payloads)
        replacement = {
            **manifest,
            'entries': entries,
            'sha256': _sha(data),
            'state': 'rewriting',
            'previous_sha256': manifest['sha256'],
        }
        index.upload_from_string(_json(replacement), if_generation_match=int(index.generation))
        _finish_rewrite(bucket, index, replacement, data)
    for blob in bucket.list_blobs(prefix=owner_prefix(SOURCE_PREFIX, uid)):
        capture = json.loads(blob.metadata['capture'])
        ranges = _retarget_ranges(bucket, uid, capture['conversation_ranges'])
        if ranges != capture['conversation_ranges']:
            capture['conversation_ranges'] = ranges
            blob.metadata = {**blob.metadata, 'capture': _json(capture).decode()}
            blob.patch(if_generation_match=int(blob.generation))


def _retarget_ranges(bucket: Any, uid: str, ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        (
            {**row, 'conversation_id': conversation_chain(bucket, uid, row['conversation_id'])[-1]}
            if row.get('conversation_id')
            else row
        )
        for row in ranges
    ]


def pcm_capture_ranges(
    chunks: list[dict[str, Any]], conversation_id: str, sample_rate: int | None
) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    offset = 0
    for chunk in sorted(chunks, key=lambda c: c['timestamp']):
        span = chunk.get('span') or {}
        rate = span.get('sample_rate') or sample_rate
        samples = span.get('samples', len(chunk['data']) // 2)
        start = float(span.get('start', chunk['timestamp']))
        ranges.append(
            {
                'conversation_id': conversation_id,
                'start': start,
                'end': start + samples / rate if rate and rate > 0 else None,
                'samples': samples,
                'sample_rate': rate,
                'plaintext_byte_start': offset,
                'plaintext_byte_length': len(chunk['data']),
            }
        )
        offset += len(chunk['data'])
    return ranges
