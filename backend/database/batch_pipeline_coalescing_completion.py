"""Original receipt completion in the merged projection's atomic transaction.

Membership is committed with unit admission, before a worker can complete.
Read every original before any write; projection's live privacy/binding guard
remains the authority for completion. No poll or surviving hold row is needed.
"""

from datetime import datetime, timedelta, timezone

from config.batch_pipeline_coalescing import MAX_MEMBERS
from database.sync_ledger import LEDGER_RETENTION_DAYS, is_valid_completed_sync_content_result, sync_content_ledger_ref


def manifest(group):
    if group is None or group['mode'] != 'merged':
        return {}
    return {
        'coalescing': {
            'group_id': group['id'],
            'members': [
                {key: member[key] for key in ('job_id', 'content_id', 'original_units')} for member in group['members']
            ],
        }
    }


def prepare(client, namespace, transaction, binding, ledger):
    metadata = ledger.get('coalescing')
    if metadata is None:
        return []  # Ordinary uploads add no reads or writes.
    members = metadata['members']
    if not 0 < len(members) <= MAX_MEMBERS or len({m['job_id'] for m in members}) != len(members):
        raise ValueError('invalid original receipt membership')
    prepared = []
    for member in members:
        intake_ref = client.collection(f'{namespace}_intakes').document(member['job_id'])
        content_ref = sync_content_ledger_ref(client, binding.owner_id, member['content_id'])
        intake = intake_ref.get(transaction=transaction).to_dict() or {}
        content = content_ref.get(transaction=transaction).to_dict() or {}
        if ledger.get('status') == 'completed' and not intake and not content:
            continue  # Terminal replay after the original receipt's TTL.
        if (
            intake.get('owner_id') != binding.owner_id
            or intake.get('conversation_id') != binding.target_conversation_id
            or intake.get('privacy_generation') != binding.privacy_generation
            or intake.get('content_id') != member['content_id']
            or intake.get('coalesce_group') != metadata['group_id']
            or intake.get('coalesce_target') not in (None, binding.job_id)
            or intake.get('original_units') != member['original_units']
            or content.get('job_id') != member['job_id']
            or content.get('dispatch_protocol') != 'batch_v1'
            or not isinstance(member['original_units'], int)
            or isinstance(member['original_units'], bool)
            or member['original_units'] <= 0
        ):
            raise ValueError('original receipt completion identity changed')
        if content.get('status') == 'completed':
            if not is_valid_completed_sync_content_result(content.get('result')):
                raise ValueError('invalid original completion')
            continue  # Do not extend terminal retention on retries or polls.
        prepared.append((intake_ref, content_ref, member, binding.job_id))
    return prepared


def write(transaction, prepared, result, now):
    """Write-only after all siblings, privacy fences and original rows were read."""
    if prepared and not is_valid_completed_sync_content_result(result):
        raise ValueError('original receipts require full authoritative completion')
    stamp = datetime.fromtimestamp(now, timezone.utc)
    expires = stamp + timedelta(days=LEDGER_RETENTION_DAYS)
    for intake_ref, content_ref, member, target in prepared:
        transaction.update(intake_ref, {'coalesce_target': target, 'expires_at': expires})
        transaction.update(
            content_ref,
            {
                'status': 'completed',
                'result': {**result, 'total_segments': member['original_units']},
                'updated_at': stamp,
                'expires_at': expires,
            },
        )
