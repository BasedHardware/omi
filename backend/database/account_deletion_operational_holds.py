"""Release only operator-proven operational holds during an account wipe.

An untagged GCS temporary hold is not deletion authority. Legacy preservation
campaigns must supply a reviewed, exact-generation plan on the server-owned
deletion marker. Legal holds, retention, and unknown metadata remain protected.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.legal_holds import assert_account_deletion_permitted, assert_destructive_gate_still_ours

# The preservation operator's COMPLETE.json receipt (2026-10-18T13:05:24Z).
# These are opaque control-artifact integrity bindings, not account identifiers.
PRESERVATION_LEDGER_SHA256 = {
    'source-index.sqlite': '03dae01244eb564f758d804511c3e3467bf58b0d6144d8ce0265916d835bdc56',
    'final-audit.sqlite': '6a4536d4150d688478a83fd05e0d6232a1288c14d11a282d774e01d2226189c4',
}


class OperationalStorageHoldBlocked(RuntimeError):
    """A hold cannot be proved operational and authorized for this wipe."""


def assert_no_protected_object_hold(blob: Any) -> None:
    """Custom legal markers protect unheld and unapproved generations too."""
    retention = getattr(blob, 'retention', None)
    metadata = getattr(blob, 'metadata', None) or {}
    if (
        getattr(blob, 'event_based_hold', False)
        or getattr(retention, 'mode', None)
        or getattr(retention, 'retain_until_time', None)
        or getattr(blob, 'retention_expiration_time', None)
        or not isinstance(metadata, dict)
        or any(
            any(marker in str(key).lower() for marker in ('legal', 'hold', 'retention', 'litigation', 'compliance'))
            for key in metadata
        )
    ):
        raise OperationalStorageHoldBlocked('legal, retention, or unknown object hold metadata is protected')


def delete_owner_bucket_prefix(
    bucket: Any, prefix: str, *, real_gcs: bool, account_deletion_uid: str | None = None
) -> int:
    """Purge and verify owner generations, honoring approved operational holds."""
    listing_kwargs = {'versions': True} if real_gcs else {}
    blobs = list(bucket.list_blobs(prefix=prefix, **listing_kwargs))
    for blob in blobs:
        if account_deletion_uid is not None:
            assert_no_protected_object_hold(blob)
        if account_deletion_uid is not None and (
            getattr(blob, 'temporary_hold', None) is True or getattr(bucket, 'name', None) == 'syncing-local'
        ):
            release_operational_hold_for_account_deletion(account_deletion_uid, blob)
        if real_gcs:
            blob.delete(if_generation_match=blob.generation, if_metageneration_match=blob.metageneration)
        else:
            blob.delete()
    if list(bucket.list_blobs(prefix=prefix, **listing_kwargs)):
        raise RuntimeError('owner storage purge left objects under the owner prefix')
    return len(blobs)


def plan_digest(plan: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def object_digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def validate_release_plan(uid: str, approval: Any) -> dict[str, Any]:
    if not isinstance(approval, dict) or approval.get('issuer') != 'reviewed_operator':
        raise OperationalStorageHoldBlocked('operational hold release needs reviewed operator approval')
    plan = approval.get('plan')
    if (
        not isinstance(plan, dict)
        or plan.get('schema_version') != 1
        or plan.get('campaign') != 'expiry-20261017'
        or plan.get('campaign_ledger_sha256') != plan_digest(PRESERVATION_LEDGER_SHA256)
        or plan.get('owner_sha256') != object_digest(uid)
        or not isinstance(approval.get('approval_ref'), str)
        or not approval['approval_ref'].strip()
        or approval.get('plan_sha256') != plan_digest(plan)
    ):
        raise OperationalStorageHoldBlocked('operational hold release approval is malformed or changed')
    objects = plan.get('objects')
    if not isinstance(objects, list) or not objects or len(objects) > 1000:
        raise OperationalStorageHoldBlocked('operational hold release plan size is invalid')
    seen = set()
    for item in objects:
        if not isinstance(item, dict):
            raise OperationalStorageHoldBlocked('operational hold release object is malformed')
        identity = (item.get('bucket'), item.get('object_sha256'), item.get('generation'))
        if (
            item.get('bucket') != 'syncing-local'
            or not isinstance(item.get('object_sha256'), str)
            or len(item['object_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in item['object_sha256'])
            or any(
                not isinstance(item.get(k), str) or not item[k].isascii() or not item[k].isdigit()
                for k in ('generation', 'metageneration')
            )
            or identity in seen
        ):
            raise OperationalStorageHoldBlocked('operational hold release object identity is invalid')
        seen.add(identity)
    return plan


def release_operational_hold_for_account_deletion(uid: str, blob: Any, *, firestore_client: Any | None = None) -> None:
    """CAS-release one approved generation and retain a content-free receipt.

    The account worker already owns the destructive gate. A pending receipt
    precedes the PATCH; a retry reconciles an ambiguous success without ever
    granting approval for a replacement generation or metageneration.
    """
    assert_no_protected_object_hold(blob)
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    marker_ref = account_deletion_document(uid, firestore_client=client)
    snapshot = marker_ref.get()
    marker = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if marker.get('wipe_status') != 'running':
        raise OperationalStorageHoldBlocked('operational hold release requires a running account wipe')
    approval = marker.get('operational_hold_release_approval')
    if approval is None and blob.temporary_hold is not True:
        return
    plan = validate_release_plan(uid, approval)
    name_hash = object_digest(blob.name)
    generation = str(blob.generation)
    match = next(
        (
            item
            for item in plan['objects']
            if item['bucket'] == blob.bucket.name
            and item['object_sha256'] == name_hash
            and item['generation'] == generation
        ),
        None,
    )
    if match is None and blob.temporary_hold is not True:
        return
    if match is None or not blob.name.startswith(f'syncing/{uid}/'):
        raise OperationalStorageHoldBlocked('held object is outside the approved operational release plan')
    token = f'account-deletion:{uid}'

    def check_authority() -> None:
        assert_destructive_gate_still_ours(uid, 'account_deletion', token=token, firestore_client=client)
        assert_account_deletion_permitted(uid, firestore_client=client)

    check_authority()
    # A generation-bound Blob keeps reload/PATCH on the same version. Never
    # release event-based holds, object retention, or equivalent legal markers.
    blob.reload(if_generation_match=int(generation))
    assert_no_protected_object_hold(blob)
    metadata = blob.metadata or {}
    known_tags = {'incident', 'source_sha256', 'source_generation'}
    if (
        blob.event_based_hold
        or blob.retention.mode
        or blob.retention.retain_until_time
        or blob.retention_expiration_time
        or (metadata and (set(metadata) - known_tags or metadata.get('incident') != plan['campaign']))
    ):
        raise OperationalStorageHoldBlocked('legal, retention, or unknown object hold metadata is protected')
    receipt_ref = marker_ref.collection('operational_hold_releases').document(f'{name_hash}-{generation}')
    receipt_snapshot = receipt_ref.get()
    receipt = (receipt_snapshot.to_dict() or {}) if receipt_snapshot.exists else {}
    expected_meta = match['metageneration']
    receipt_identity = {
        'schema_version': 1,
        'plan_sha256': plan_digest(plan),
        'campaign': plan['campaign'],
        'bucket': blob.bucket.name,
        'object_sha256': name_hash,
        'generation': generation,
        'approved_metageneration': expected_meta,
    }
    if blob.temporary_hold is not True:
        # PATCH can succeed before the response/receipt write reaches us. Only
        # reconcile the one metadata increment proved by our prior intent.
        if (
            all(receipt.get(k) == v for k, v in receipt_identity.items())
            and receipt.get('state') in {'release_pending', 'released'}
            and str(blob.metageneration) == str(int(expected_meta) + 1)
        ):
            check_authority()
            receipt_ref.set(
                {
                    **receipt_identity,
                    'state': 'released',
                    'released_metageneration': str(blob.metageneration),
                    'updated_at': datetime.now(timezone.utc),
                }
            )
            return
        if not receipt:
            # No release by this worker: the ordinary authorized wipe may
            # delete an already-unheld object, without claiming we released it.
            return
        raise OperationalStorageHoldBlocked('unheld object has no matching operational release receipt')
    if str(blob.metageneration) != expected_meta:
        raise OperationalStorageHoldBlocked('operational hold metadata changed since approval')
    check_authority()
    receipt_ref.set({**receipt_identity, 'state': 'release_pending', 'updated_at': datetime.now(timezone.utc)})
    check_authority()
    blob.temporary_hold = False
    blob.patch(if_generation_match=int(generation), if_metageneration_match=int(expected_meta))
    receipt_ref.set(
        {
            **receipt_identity,
            'state': 'released',
            'released_metageneration': str(blob.metageneration),
            'updated_at': datetime.now(timezone.utc),
        }
    )
