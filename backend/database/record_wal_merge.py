"""Persist and flatten the bounded lineage of already-settled native WALs."""

from config.record_wal_duplicate import MERGE_TARGET_FIELD, RETAINED_DONORS_FIELD, SETTLED_FIELD

MAX_RETAINED_DONORS = 16


class RetainedMergeDeferred(RuntimeError):
    """Source retraction must wait until its complete retained lineage can be published."""


def _lineage(values):
    if not isinstance(values, list) or len(values) > MAX_RETAINED_DONORS:
        raise RetainedMergeDeferred('unbounded retained donor lineage')
    if any(type(value) is not str or not value or '/' in value for value in values):
        raise RetainedMergeDeferred('invalid retained donor lineage')
    if len(set(values)) != len(values):
        raise RetainedMergeDeferred('duplicate retained donor lineage')
    return values


def plan_retention(sources):
    """Derive the immutable admission choice from the already locked source rows."""
    plans = {}
    original_ids = set()
    for cid, row in sources.items():
        inherited = _lineage(row.get(RETAINED_DONORS_FIELD, []))
        if not inherited and row.get(SETTLED_FIELD) is not True:
            continue
        ancestors = set(row.get('sync_merged_from') or ())
        if set(inherited) - ancestors or inherited and ancestors != set(inherited):
            raise RetainedMergeDeferred('unqualified inherited erase lineage')
        keep = row.get(SETTLED_FIELD) is True
        if keep and ancestors != set(inherited):
            raise RetainedMergeDeferred('unqualified retained source ancestry')
        ids = [*inherited, *([cid] if keep else [])]
        if original_ids.intersection(ids) or set(inherited).intersection(sources):
            raise RetainedMergeDeferred('conflicting retained donor lineage')
        original_ids.update(ids)
        if len(original_ids) > MAX_RETAINED_DONORS:
            raise RetainedMergeDeferred('retained donor limit')
        plans[cid] = {'keep': keep, 'inherited': sorted(inherited)}
    return plans


def publication(tx, owner, sources, target_id, target, expected):
    """Read the whole erase conflict set before preparing any merge writes."""
    plans = plan_retention(sources)
    if plans != expected:
        raise RetainedMergeDeferred('retained merge admission changed')
    if not plans:
        return {}
    if (
        target_id in sources
        or target.get(RETAINED_DONORS_FIELD)
        or target.get(MERGE_TARGET_FIELD)
        or target.get('private_cloud_sync_enabled') is not True
        or target.get('uses_custom_stt')
    ):
        raise RetainedMergeDeferred('retained merge destination already bound')
    conversations = owner.collection('conversations')
    tombstones = owner.collection('deleted_conversations')
    original_ids = set()
    patches = {}
    for cid, plan in plans.items():
        inherited = plan['inherited']
        if tombstones.document(cid).get(transaction=tx).exists:
            raise RetainedMergeDeferred('erased merge source')
        if inherited:
            patches[cid] = {RETAINED_DONORS_FIELD: [], 'sync_merged_from': []}
        for donor in inherited:
            raw = conversations.document(donor).get(transaction=tx).to_dict() or {}
            if (
                donor == target_id
                or raw.get(SETTLED_FIELD) is not True
                or raw.get(MERGE_TARGET_FIELD) != cid
                or raw.get('sync_merged_into') != cid
                or raw.get('deleted') is not True
                or tombstones.document(donor).get(transaction=tx).exists
            ):
                raise RetainedMergeDeferred('retained donor authority changed')
            patches[donor] = {MERGE_TARGET_FIELD: target_id, 'sync_merged_into': target_id}
            original_ids.add(donor)
        if plan['keep']:
            patches.setdefault(cid, {}).update(
                {MERGE_TARGET_FIELD: target_id, 'sync_merged_into': target_id, 'deleted': True, 'discarded': True}
            )
            original_ids.add(cid)
    if tombstones.document(target_id).get(transaction=tx).exists:
        raise RetainedMergeDeferred('erased merge destination')
    patches[target_id] = {
        RETAINED_DONORS_FIELD: sorted(original_ids),
        'sync_merged_from': sorted({*(target.get('sync_merged_from') or ()), *original_ids}),
    }
    return patches
