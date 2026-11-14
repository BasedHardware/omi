"""Separate original-upload cold-key census; never a terminal-session proof.

The original manifest is immutable and predates result reservations. This
extension binds each new cold key to that original paid attempt and lifetime.
Capabilities remain solely in the inflight registry, never in cold packets.
Callers hold owner X until this census commits, before any remote I/O.
"""

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.fs_fence import handoff_ref
from database.jobstore.postgres_store import jsonb
from database.privacy_fence.protocol import row_dict

FAMILY = 'queue_provider_uploads'
IMMUTABLE = (
    'namespace',
    'unit_id',
    'recording_id',
    'owner_key',
    'attempt_token',
    'admission_id',
    'object_key',
    'bucket',
    'content_hash',
    'original_deadline',
)
FIELDS = frozenset((*IMMUTABLE, 'phase', 'effect_id', 'generation'))
HISTORY = {
    'prepared': {'prepared'},
    'registered': {'prepared', 'registered'},
    'draining': {'prepared', 'registered', 'draining'},
    'published': {'prepared', 'registered', 'published'},
    'fenced': {'prepared', 'registered', 'draining', 'fenced'},
}


def descriptor(row):
    return {key: str(row[key]) if key == 'admission_id' else row[key] for key in IMMUTABLE}


def retain(conn, handoff, original, identity, body):
    if set(identity) != {'unit_id', 'recording_id'} or identity['recording_id'] != original['identity']:
        raise AuthorityRefused('upload cold identity changed')
    upload = row_dict(
        conn,
        'SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s',
        (handoff.ticket.namespace, identity['unit_id']),
    )
    jobs = original['intent']['payload']['jobs']
    if (
        not upload
        or identity['unit_id'] not in jobs
        or upload['recording_id'] != original['identity']
        or upload['owner_key'] != original['owner_key']
        or str(upload['admission_id']) != original['admission']['admission_id']
        or upload['original_deadline'] != jobs[identity['unit_id']]['typed_provider']['custody_deadline']
        or not isinstance(body, dict)
        or set(body) != FIELDS
        or descriptor(body) != descriptor(upload)
        or body['phase'] not in HISTORY[upload['phase']]
        or (body['effect_id'] is not None and str(body['effect_id']) != str(upload['effect_id']))
        or (body['generation'] is not None and body['generation'] != upload['generation'])
        or (body['phase'] == 'prepared' and (body['effect_id'] is not None or body['generation'] is not None))
        or (body['phase'] != 'prepared' and body['effect_id'] is None)
    ):
        raise AuthorityRefused('upload cold source/admission/lifetime changed')
    source = descriptor(upload)
    path = handoff_ref(handoff.client, handoff.ticket.namespace, 'cold_' + FAMILY, fingerprint(identity)).path
    digest = fingerprint(dict(intent=original['intent'], admission=original['admission']))
    expected = (original['identity'], original['owner_key'], digest, source, path)
    old = conn.execute(
        'SELECT recording_id,owner_key,source_fingerprint,original_upload,cold_path '
        'FROM queue_upload_cold_custody WHERE namespace=%s AND unit_id=%s',
        (handoff.ticket.namespace, identity['unit_id']),
    ).fetchone()
    if old and old != expected:
        raise AuthorityRefused('immutable original upload cold custody changed')
    if not old:
        conn.execute(
            'INSERT INTO queue_upload_cold_custody(namespace,unit_id,recording_id,owner_key,'
            'source_fingerprint,original_upload,cold_path) VALUES (%s,%s,%s,%s,%s,%s,%s)',
            (handoff.ticket.namespace, identity['unit_id'], *expected[:3], jsonb(source), path),
        )
    return path
