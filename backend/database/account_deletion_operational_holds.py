"""Release only operator-proven operational holds during an account wipe.

An untagged GCS temporary hold is not deletion authority. Legacy preservation
campaigns must supply a reviewed, exact-generation plan on the server-owned
deletion marker. Legal holds, retention, and unknown metadata remain protected.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, TypeGuard

from google.api_core.exceptions import Forbidden, GoogleAPICallError, NotFound, PreconditionFailed

from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.legal_holds import assert_account_deletion_permitted, assert_destructive_gate_still_ours

OPERATIONAL_HOLD_RELEASE_PLAN_MAX_OBJECTS = 20_000
OPERATIONAL_HOLD_RELEASE_PLAN_SHARDS = 'operational_hold_release_plan_shards'
_HASH_PREFIX_LAYOUT = 'sha256-prefix-v1'

# The preservation operator's COMPLETE.json receipt (2026-10-18T13:05:24Z).
# These are opaque control-artifact integrity bindings, not account identifiers.
PRESERVATION_LEDGER_SHA256 = {
    'source-index.sqlite': '03dae01244eb564f758d804511c3e3467bf58b0d6144d8ce0265916d835bdc56',
    'final-audit.sqlite': '6a4536d4150d688478a83fd05e0d6232a1288c14d11a282d774e01d2226189c4',
}


class OperationalStorageHoldBlocked(RuntimeError):
    """A hold cannot be proved operational and authorized for this wipe."""


class StoragePrefixPurgeError(RuntimeError):
    """A conversation storage sweep failed verification or a provider request."""


class StoragePrefixPurgeBlocked(StoragePrefixPurgeError):
    """Named object generations remain protected by Cloud Storage."""

    def __init__(self, objects: dict[tuple[str, str, int], str], *, unverified: int = 0):
        self.objects = objects
        self.unverified = unverified
        super().__init__(
            'owner storage purge left objects under the owner prefix: ' f'blocked={objects!r}, unverified={unverified}'
        )


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
    bucket: Any,
    prefix: str,
    *,
    real_gcs: bool,
    account_deletion_uid: str | None = None,
    tolerate_object_races: bool = True,
    object_name_allowed: Callable[[str], bool] | None = None,
) -> int:
    """Purge and verify owner generations, honoring approved operational holds.

    ``object_name_allowed`` scopes both deletion and verification when a raw
    storage prefix can contain complete generated names owned by another UID.
    Every retained candidate still passes the same hold and generation gates.
    """
    listing_kwargs = {'versions': True} if real_gcs else {}
    if account_deletion_uid is None and tolerate_object_races:
        return _delete_conversation_bucket_prefix(
            bucket,
            prefix,
            real_gcs=real_gcs,
            listing_kwargs=listing_kwargs,
            object_name_allowed=object_name_allowed,
        )

    blobs = [
        blob
        for blob in bucket.list_blobs(prefix=prefix, **listing_kwargs)
        if object_name_allowed is None or object_name_allowed(blob.name)
    ]
    for blob in blobs:
        if account_deletion_uid is not None:
            assert_no_protected_object_hold(blob)
            if getattr(blob, 'temporary_hold', None) is True or getattr(bucket, 'name', None) == 'syncing-local':
                release_operational_hold_for_account_deletion(account_deletion_uid, blob)
        if real_gcs:
            blob.delete(if_generation_match=blob.generation, if_metageneration_match=blob.metageneration)
        else:
            blob.delete()
    if any(
        object_name_allowed is None or object_name_allowed(blob.name)
        for blob in bucket.list_blobs(prefix=prefix, **listing_kwargs)
    ):
        raise RuntimeError('owner storage purge left objects under the owner prefix')
    return len(blobs)


def _storage_error_reason(error: GoogleAPICallError) -> str:
    return next((item['reason'] for item in error.errors if item.get('reason')), type(error).__name__)


def _delete_conversation_bucket_prefix(
    bucket: Any,
    prefix: str,
    *,
    real_gcs: bool,
    listing_kwargs: dict[str, bool],
    object_name_allowed: Callable[[str], bool] | None = None,
) -> int:
    def list_versions() -> list[Any]:
        try:
            return [
                blob
                for blob in bucket.list_blobs(prefix=prefix, **listing_kwargs)
                if object_name_allowed is None or object_name_allowed(blob.name)
            ]
        except GoogleAPICallError as error:
            raise StoragePrefixPurgeError(
                f'owner storage list failed in {bucket.name}: {_storage_error_reason(error)}'
            ) from None

    blocked: dict[tuple[str, str, int], str] = {}
    deleted = 0
    for blob in list_versions():
        try:
            if real_gcs:
                blob.delete(if_generation_match=blob.generation, if_metageneration_match=blob.metageneration)
            else:
                blob.delete()
        except GoogleAPICallError as error:
            reason = _storage_error_reason(error)
            # A generic object DELETE 404 can also mean the bucket vanished.
            # The final LIST verifies that the bucket is still accessible.
            if isinstance(error, NotFound) and reason in {'notFound', 'noSuchObject', 'NotFound'}:
                continue
            if isinstance(error, PreconditionFailed) and reason == 'conditionNotMet':
                continue
            if isinstance(error, Forbidden) and reason in {'objectUnderActiveHold', 'retentionPolicyNotMet'}:
                blocked[(bucket.name, blob.name, blob.generation)] = reason
                continue
            raise StoragePrefixPurgeError(f'owner storage delete failed in {bucket.name}: {reason}') from None
        deleted += 1

    remaining = list_versions()
    if remaining:
        present = {(bucket.name, blob.name, blob.generation) for blob in remaining} if blocked else set()
        blocked = {key: reason for key, reason in blocked.items() if key in present}
        if blocked:
            raise StoragePrefixPurgeBlocked(blocked, unverified=len(remaining) - len(blocked))
        raise StoragePrefixPurgeError('owner storage purge left objects under the owner prefix')
    return deleted


def plan_digest(plan: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def object_digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def _validate_release_header(uid: str, approval: Any) -> dict[str, Any]:
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
    ):
        raise OperationalStorageHoldBlocked('operational hold release approval is malformed or changed')
    return plan


def _validate_release_objects(objects: Any) -> TypeGuard[list[dict[str, Any]]]:
    if not isinstance(objects, list) or not objects or len(objects) > OPERATIONAL_HOLD_RELEASE_PLAN_MAX_OBJECTS:
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
    return True


def validate_release_plan(uid: str, approval: Any) -> dict[str, Any]:
    plan = _validate_release_header(uid, approval)
    if approval.get('plan_sha256') != plan_digest(plan):
        raise OperationalStorageHoldBlocked('operational hold release approval is malformed or changed')
    _validate_release_objects(plan.get('objects'))
    return plan


def shard_release_approval(uid: str, approval: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    plan = validate_release_plan(uid, approval)
    shards: dict[str, dict[str, Any]] = {}
    for item in plan['objects']:
        prefix = item['object_sha256'][:2]
        shards.setdefault(prefix, {'objects': []})['objects'].append(item)
    manifest = {
        **approval,
        'layout': _HASH_PREFIX_LAYOUT,
        'plan': {key: value for key, value in plan.items() if key != 'objects'},
        'shard_sha256': {prefix: plan_digest(shard) for prefix, shard in shards.items()},
    }
    return {**manifest, 'manifest_sha256': plan_digest(manifest)}, shards


def _read_release_objects(uid: str, marker_ref: Any, approval: Any, prefix: str) -> list[dict[str, Any]]:
    if not isinstance(approval, dict) or 'layout' not in approval:
        return validate_release_plan(uid, approval)['objects']

    plan = _validate_release_header(uid, approval)
    manifest = {key: value for key, value in approval.items() if key != 'manifest_sha256'}
    shard_hashes = approval.get('shard_sha256')
    if (
        approval['layout'] != _HASH_PREFIX_LAYOUT
        or 'objects' in plan
        or not isinstance(shard_hashes, dict)
        or approval.get('manifest_sha256') != plan_digest(manifest)
    ):
        raise OperationalStorageHoldBlocked('operational hold release manifest is malformed or changed')
    if prefix not in shard_hashes:
        return []

    snapshot = marker_ref.collection(OPERATIONAL_HOLD_RELEASE_PLAN_SHARDS).document(prefix).get()
    shard = snapshot.to_dict() if snapshot.exists else None
    if not isinstance(shard, dict) or shard_hashes[prefix] != plan_digest(shard):
        raise OperationalStorageHoldBlocked('operational hold release shard is missing or changed')
    objects = shard.get('objects')
    _validate_release_objects(objects)
    if not isinstance(objects, list):
        raise OperationalStorageHoldBlocked('operational hold release plan size is invalid')
    validated: list[dict[str, Any]] = [item for item in objects if isinstance(item, dict)]
    if any(item['object_sha256'][:2] != prefix for item in validated):
        raise OperationalStorageHoldBlocked('operational hold release shard contains an invalid object prefix')
    return validated


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
    name_hash = object_digest(blob.name)
    generation = str(blob.generation)
    objects = _read_release_objects(uid, marker_ref, approval, name_hash[:2])
    match = next(
        (
            item
            for item in objects
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
    if not isinstance(approval, dict):
        raise OperationalStorageHoldBlocked('operational hold release approval is missing')
    metadata = blob.metadata or {}
    campaign = approval['plan']['campaign']
    known_tags = {'incident', 'source_sha256', 'source_generation'}
    if (
        blob.event_based_hold
        or blob.retention.mode
        or blob.retention.retain_until_time
        or blob.retention_expiration_time
        or (metadata and (set(metadata) - known_tags or metadata.get('incident') != campaign))
    ):
        raise OperationalStorageHoldBlocked('legal, retention, or unknown object hold metadata is protected')
    receipt_ref = marker_ref.collection('operational_hold_releases').document(f'{name_hash}-{generation}')
    receipt_snapshot = receipt_ref.get()
    receipt = (receipt_snapshot.to_dict() or {}) if receipt_snapshot.exists else {}
    expected_meta = match['metageneration']
    receipt_identity = {
        'schema_version': 1,
        'plan_sha256': approval['plan_sha256'],
        'campaign': campaign,
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
