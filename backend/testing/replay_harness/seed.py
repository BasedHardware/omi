"""Seed WP2 owner-ciphertext documents without keys, decryption, or remote blobs.

WP2 capture_schema v1 / capture_prod.capture_owner_item emits conversation,
finalization_jobs, enrichment_outbox, jobs/results/artifacts and chunk_inventory.
Only local synthetic identities are used in the emulator. Ciphertext stays opaque;
these boundaries can diagnose custody and missing finalization from metadata alone.
"""

from copy import deepcopy
from datetime import datetime
import hashlib


def restore_dates(value):
    if isinstance(value, dict):
        return {key: restore_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [restore_dates(item) for item in value]
    if isinstance(value, str):
        try:
            if 'T' in value:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
    return value


def seed_case(case, environment):
    if hasattr(environment, 'conversation_ref'):
        return environment.conversation_ref
    corpus = case.corpus
    row = restore_dates(deepcopy(corpus.get('conversation')))
    if not isinstance(row, dict):
        raise ValueError('conversation document required')
    uid = environment.harness.seed_user('synthetic-replay-titling')
    environment.harness.replay_users = [*getattr(environment.harness, 'replay_users', []), uid]
    cid = 'synthetic-replay-conversation'
    ref = environment.store.client.collection('users').document(uid).collection('conversations').document(cid)
    # Replace tokens recursively, never interpolate a captured identifier in a path.
    identities = {corpus.get('owner_token', uid): uid, corpus.get('conversation_id', row.get('id', cid)): cid}
    job_ids = {key: f'{uid}-finalization-{index}' for index, key in enumerate(corpus.get('finalization_jobs', {}))}
    identities.update(job_ids)

    def remap(value):
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        if isinstance(value, list):
            return [remap(item) for item in value]
        return identities.get(value, value) if isinstance(value, str) else value

    row = remap(row)
    row['id'] = cid
    ref.set(row)
    environment.replay_documents = []
    for table in ('jobs', 'results', 'artifacts'):
        for index, document in enumerate(corpus.get(table, {}).values()):
            target = environment.store.client.collection(f'{environment.store.namespace}_{table}').document(str(index))
            target.set(remap(restore_dates(document)))
    for key, document in corpus.get('finalization_jobs', {}).items():
        target = environment.store.client.collection('conversation_finalization_jobs').document(job_ids[key])
        target.set({**remap(restore_dates(document)), 'id': job_ids[key], 'uid': uid, 'conversation_id': cid})
        environment.replay_documents.append(target)
    if corpus.get('enrichment_outbox'):
        key = hashlib.sha256(f'{uid}\0{cid}'.encode()).hexdigest()
        target = environment.store.client.collection('sync_reprocess_outbox').document(key)
        target.set(remap(restore_dates(corpus['enrichment_outbox'])))
        environment.replay_documents.append(target)
    environment.conversation_ref = ref
    environment.replay_uid, environment.replay_cid = uid, cid
    return ref
