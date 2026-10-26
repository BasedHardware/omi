#!/usr/bin/env python3
"""Metadata-only plan, or explicitly approved registration and queue wake.

Never clears a hold or deletes an object itself. The deployed deletion worker
revalidates authority, records receipts, releases approved holds and purges.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter

from database.legal_holds import (
    destructive_operation_gate,
    assert_destructive_operation_transaction,
    assert_account_deletion_permitted,
)
from utils.cloud_tasks import enqueue_account_deletion_wipe
from database.account_deletion_operational_holds import object_digest, plan_digest, validate_release_plan

BUCKET = 'syncing-local'
PROJECT = 'based-hardware'


def preservation_proofs(root: Path, uid: str) -> set[tuple[str, str]]:
    """Only this owner's control rows; no audio or conversation data."""
    with sqlite3.connect(f'file:{root / "source-index.sqlite"}?mode=ro', uri=True) as db:
        db.execute('ATTACH DATABASE ? AS audited', (f'file:{root / "final-audit.sqlite"}?mode=ro',))
        # LIKE wildcards in UIDs must not broaden the owner prefix.
        prefix = f'syncing/{uid}/'.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        rows = db.execute(
            "SELECT x.n,p.restored FROM sources x JOIN audited.proof p ON p.c=x.c AND p.s=x.s "
            "WHERE x.n LIKE ? ESCAPE '\\' AND p.state='held' AND p.hold=1",
            (prefix + '%',),
        ).fetchall()
    return {(object_digest(name), str(generation)) for name, generation in rows}


def build_plan(uid: str, blobs, proofs: set[tuple[str, str]]) -> dict:
    objects = []
    for blob in blobs:
        if not blob.name.startswith(f'syncing/{uid}/'):
            raise ValueError('object is outside owner prefix')
        if (
            blob.event_based_hold
            or blob.retention.mode
            or blob.retention.retain_until_time
            or blob.retention_expiration_time
        ):
            raise ValueError('protected event or retention hold requires separate disposition')
        if blob.temporary_hold is not True:
            continue
        # These legacy campaign sources have no tags. Unknown/equivalent legal
        # markers require a new review; do not erase their evidence in a plan.
        if blob.metadata:
            raise ValueError('unknown object metadata requires separate disposition')
        identity = (object_digest(blob.name), str(blob.generation))
        if identity not in proofs:
            raise ValueError('held generation has no operational preservation proof')
        objects.append(
            {
                'bucket': BUCKET,
                'object_sha256': identity[0],
                'generation': identity[1],
                'metageneration': str(blob.metageneration),
            }
        )
    if not objects:
        raise ValueError('no proven operational holds remain')
    plan = {
        'schema_version': 1,
        'campaign': 'expiry-20261017',
        'owner_sha256': object_digest(uid),
        'objects': sorted(objects, key=lambda item: (item['object_sha256'], item['generation'])),
    }
    validate_release_plan(
        uid,
        {
            'issuer': 'reviewed_operator',
            'approval_ref': 'pending-review',
            'plan': plan,
            'plan_sha256': plan_digest(plan),
        },
    )
    return plan


@firestore.transactional
def register_plan(transaction, client, uid, job_id, token, approval):
    assert_destructive_operation_transaction(transaction, client, uid=uid, kind='account_deletion', token=token)
    ref = client.collection('account_deletions').document(uid)
    snapshot = ref.get(transaction=transaction)
    marker = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if marker.get('wipe_status') != 'failed' or marker.get('wipe_job_id') != job_id:
        raise ValueError('deletion job changed or is no longer failed')
    existing = marker.get('operational_hold_release_approval')
    if existing is not None and existing != approval:
        raise ValueError('existing operational approval must not be overwritten')
    transaction.update(ref, {'operational_hold_release_approval': approval})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--single-failed-job',
        action='store_true',
        required=True,
        help='refuse unless exactly one failed deletion exists',
    )
    parser.add_argument('--preservation-audit-dir', type=Path, required=True)
    parser.add_argument('--plan-output', type=Path)
    parser.add_argument('--approved-plan', type=Path)
    parser.add_argument('--apply-digest')
    parser.add_argument('--approval-ref')
    parser.add_argument('--enqueue', action='store_true')
    parser.add_argument('--handler-url', help='live backend-sync deletion handler URL, from operator readback')
    args = parser.parse_args()
    applying = args.apply_digest is not None
    tier = os.environ.get('GCP_AGENT_TIER')
    if tier not in {'ro-prod', 'prod-operator'} or (applying and tier != 'prod-operator'):
        raise ValueError('select ro-prod for plans or approved prod-operator for registration')
    if applying and (not args.approved_plan or not args.approval_ref):
        raise ValueError('apply needs the reviewed plan and approval reference')
    if args.enqueue:
        endpoint = urlsplit(args.handler_url or '')
        if (
            not applying
            or endpoint.scheme != 'https'
            or not endpoint.hostname
            or not endpoint.hostname.startswith('backend-sync-')
            or not endpoint.hostname.endswith('.run.app')
            or endpoint.path != '/v1/users/account-deletion-wipes/run'
            or endpoint.username
            or endpoint.password
            or endpoint.port
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError('queue wake needs approved registration and the verified backend-sync handler')
    client = firestore.Client(project=PROJECT)
    docs = list(
        client.collection('account_deletions')
        .where(filter=FieldFilter('wipe_status', '==', 'failed'))
        .select(['wipe_status', 'wipe_job_id'])
        .limit(2)
        .stream()
    )
    if len(docs) != 1:
        raise ValueError('expected exactly one failed deletion; no account selected')
    uid = docs[0].id
    job_id = (docs[0].to_dict() or {}).get('wipe_job_id')
    if not isinstance(job_id, str) or not job_id:
        raise ValueError('existing opaque deletion job is missing')
    assert_account_deletion_permitted(uid, firestore_client=client)
    blobs = storage.Client(project=PROJECT).list_blobs(
        BUCKET,
        prefix=f'syncing/{uid}/',
        versions=True,
        fields='nextPageToken,items(name,generation,metageneration,temporaryHold,eventBasedHold,retention,retentionExpirationTime,metadata)',
    )
    plan = build_plan(uid, blobs, preservation_proofs(args.preservation_audit_dir, uid))
    digest = plan_digest(plan)
    if args.plan_output:
        fd = os.open(args.plan_output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump({'plan': plan, 'plan_sha256': digest}, handle, sort_keys=True, indent=2)
    print(
        json.dumps(
            {'mode': 'register' if applying else 'dry-run', 'object_count': len(plan['objects']), 'plan_sha256': digest}
        ),
        flush=True,
    )
    if not applying:
        return
    reviewed = json.loads(args.approved_plan.read_text())
    if reviewed.get('plan') != plan or reviewed.get('plan_sha256') != digest or args.apply_digest != digest:
        raise ValueError('reviewed plan differs from fresh owner-generation metadata')
    approval = {'issuer': 'reviewed_operator', 'approval_ref': args.approval_ref, 'plan': plan, 'plan_sha256': digest}
    with destructive_operation_gate(uid, kind='account_deletion', firestore_client=client) as token:
        register_plan(client.transaction(), client, uid, job_id, token, approval)
    print(json.dumps({'registered': True, 'at': datetime.now(timezone.utc).isoformat()}), flush=True)
    if args.enqueue:
        os.environ.update(
            {
                'SYNC_TASKS_PROJECT': PROJECT,
                'SYNC_TASKS_LOCATION': 'us-central1',
                'SYNC_TASKS_INVOKER_SA': 'sync-tasks-invoker@based-hardware.iam.gserviceaccount.com',
                'ACCOUNT_DELETION_TASKS_QUEUE': 'account-deletion',
                'ACCOUNT_DELETION_HANDLER_URL': args.handler_url,
                'ACCOUNT_DELETION_TASKS_OIDC_AUDIENCE': args.handler_url,
            }
        )
        enqueue_account_deletion_wipe(job_id)
        print(json.dumps({'enqueued_existing_job': True}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # SDK exception strings may contain identities, paths, or credentials.
        print(json.dumps({'status': 'refused', 'error_class': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
