"""Pure original-record retained-copy census; grants no erasure authority."""

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.fs_fence import handoff_ref
from database.jobstore.provider_handoff import validate_provider_payload
from database.privacy_fence.protocol import owner_key


def original_manifest(handoff, row):
    intent = row['intent']
    binding = validate_provider_payload(intent['payload'])
    ns, identity = row['namespace'], row['identity']
    if binding.job_id != identity or owner_key(binding.owner_id) != row['owner_key']:
        raise AuthorityRefused('original recording ownership/census mismatch')
    paths = [
        handoff_ref(handoff.client, ns, 'provider_projection_' + table, identity + '/' + sid).path
        for sid in binding.segment_ids
        for table in ('jobs', 'results')
    ] + [handoff_ref(handoff.client, ns, 'provider_projection_owners', identity + '/' + row['owner_key']).path]
    cold_keys = [
        (family, key)
        for sid in binding.segment_ids
        for family, key in (
            ('units', dict(unit_id=sid, recording_id=identity)),
            ('queue_custody', dict(identity=sid)),
        )
    ] + [
        ('recordings', dict(recording_id=identity)),
        ('queue_handoffs', dict(identity=identity)),
        (
            'outbox',
            dict(kind='project_conversation', dedupe_key=identity, generation=row['admission']['admission_id']),
        ),
    ]
    return dict(
        unit_ids=list(binding.segment_ids),
        private_paths=paths,
        original_deadlines={
            sid: intent['payload']['jobs'][sid]['typed_provider']['custody_deadline'] for sid in binding.segment_ids
        },
        original_paths=[
            handoff_ref(handoff.client, ns, kind, identity).path for kind in ('intent', 'completion', 'receipt')
        ]
        + [handoff.client.collection(ns + '_intakes').document(identity).path],
        cold_barrier_path=handoff_ref(handoff.client, ns, 'cold_recording_erasure', identity).path,
        staging_barrier_path=handoff_ref(handoff.client, ns, 'staging_erasure', identity).path,
        cold_paths=[
            handoff_ref(handoff.client, ns, 'cold_' + family, fingerprint(key)).path for family, key in cold_keys
        ],
        # These are outstanding obligations, never asserted absence or a
        # fabricated object/session certificate. Their original references
        # and attempt histories remain in PG until every outcome is known.
        outstanding=['original_objects', 'original_metadata', 'paid_attempts', 'journal', 'cold_copies'],
    )
