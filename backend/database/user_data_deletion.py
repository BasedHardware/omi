"""Account-data erasure across top-level batch stores and recursive user data."""

from collections.abc import Callable
from contextlib import nullcontext

from config.refactor_modes import default_on
from database.speaker_evidence_verification import record_checked_sweep
from database.action_item_fence import fenced_action_item_commit
from database.home_feed_writer import suppress_during_account_erasure
import logging
import os
from typing import Any
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database.conversation_finalization_schema import FINALIZATION_JOBS_COLLECTION
from database._client import get_data_plane_firestore_client, run_transactional
from database.batch_account_authority import account_authority_writer_enabled, mutate_account_authority
from database.memory_collections import RELEASED_MEMORY_CHANGE_HEAD
from database.people_generation import generation_ref
from database.staged_promote_cache import invalidate_around_write
from database.apps import apps_collection, PUBLIC_APPROVED_APPS_CACHE_KEY, search_apps_db
from database.redis_db import delete_app_cache_by_id, delete_generic_cache
from utils.observability import speaker_evidence_erasure as metrics

SPEAKER_EVIDENCE_ERASURE_CHECK_ENV = 'SPEAKER_EVIDENCE_ERASURE_CHECK_ENABLED'

logger = logging.getLogger(__name__)


def purge_finalization_jobs(uid: str, client: Any) -> None:
    """Delete every job owned by uid, including on a retry with no user root."""
    query = (
        client.collection(FINALIZATION_JOBS_COLLECTION)
        .where(filter=FieldFilter('uid', '==', uid))
        .select([])
        .limit(450)
    )
    deleted = 0
    while True:
        page = list(query.stream())
        if not page:
            logger.info(
                'account_erasure_finalization_jobs_purged deleted=%d remaining=%d revision=%s',
                deleted,
                len(page),
                os.getenv('K_REVISION') or 'unknown',
            )
            return
        batch = client.batch()
        for job in page:
            batch.delete(job.reference)
        batch.commit()
        deleted += len(page)


@invalidate_around_write
@suppress_during_account_erasure
def purge_user_subtree(uid: str, client: Any, delete_collection: Callable) -> dict:
    # Top-level batch stores are outside users/{uid}; fence and purge them
    # before deleting the last references needed for retryable object erasure.
    from database.batch_pipeline_purge import purge_batch_owner

    purge_batch_owner(uid)
    # Membership is user data outside the recursive users/{uid} subtree, and it
    # lives in the customer data plane (which can differ from this compute
    # client's project). A failed delete must propagate so the account wipe
    # retries it.
    data_plane = get_data_plane_firestore_client()
    cohort_ref = data_plane.collection('rollout_cohorts').document(uid)
    # Child audit rows (go_finalization_audit) survive a parent delete, so erase them first.
    for sub in cohort_ref.collections():
        delete_collection(sub, client=data_plane)
    cohort_ref.delete()
    # Creator-owned marketplace apps live outside users/{uid}; remove their
    # nested API keys/reviews too so final and immediate erasure share parity.
    delete_generic_cache(PUBLIC_APPROVED_APPS_CACHE_KEY)
    for app in search_apps_db(uid, my_apps=True):
        app_id = app.get('id')
        if not isinstance(app_id, str) or not app_id:
            raise ValueError('creator-owned app missing id during account deletion')
        app_ref = client.collection(apps_collection).document(app_id)
        for subcollection in app_ref.collections():
            delete_collection(subcollection, client=client)
        app_ref.delete()
        delete_app_cache_by_id(app_id)
    user_ref = client.collection('users').document(uid)
    atomic_root = account_authority_writer_enabled()
    root_exists = user_ref.get().exists

    # Enumerate subcollections live even when the root document is missing.
    # Firestore permits immediate children to survive a parent deletion; an
    # early "User not found" return would falsely mark the deletion complete.
    # This picks up
    # everything the user has written (conversations, deleted_conversations, memories, action_items,
    # folders, goals, integrations, task_integrations, fcm_tokens, fair_use_*,
    # hourly_usage, meetings, screen_activity, files, people, chat_sessions,
    # messages, pipeline_ledger, and any future additions).
    for sub in user_ref.collections():
        logger.info(f"Deleting subcollection {sub.id} for user {uid}")
        with fenced_action_item_commit(uid) if sub.id == 'action_items' else nullcontext():
            delete_collection(sub, client=client)
    # A historical-source-index bump or build (database/memories.py) can land
    # after memory_state was walked; the doc holds only hashes, but drop it too.
    user_ref.collection('memory_state').document('historical_source_index').delete()
    # Atomic source deletes also maintain this derived head. Erase it after
    # every source collection, including when memory_state was visited first.
    user_ref.collection('memory_state').document(RELEASED_MEMORY_CHANGE_HEAD).delete()
    # Explicitly erase historical heads as part of account deletion, including
    # a retry whose root user document is already absent.
    for family in ('conversations', 'action_items'):
        user_ref.collection('list_serving_versions').document(family).delete()

    # People deletes can recreate their content-free generation head after
    # people_meta was enumerated. Missing metadata never authorizes memo reuse.
    generation_ref(user_ref).delete()

    if root_exists and atomic_root:
        operation_id = uuid4().hex

        @firestore.transactional
        def delete_root(transaction):
            snapshot = user_ref.get(transaction=transaction)
            if snapshot.exists:
                mutate_account_authority(transaction, user_ref, operation_id, None, client=client, preimage=snapshot)

        run_transactional(client, delete_root, transient=True)
    elif root_exists:
        logger.info(f"Deleting user document: {uid}")
        user_ref.delete()
    _sweep_speaker_evidence(uid, data_plane, delete_collection)
    purge_finalization_jobs(uid, client)
    return {'status': 'ok', 'message': 'Account deleted successfully'}


def _sweep_speaker_evidence(uid: str, data_plane: Any, delete_collection: Callable) -> None:
    # A child can arrive between the first sweep and parent deletion.
    # list_documents includes missing parents with surviving descendants.
    metrics.SWEEP_STARTED.inc()
    verify = default_on(SPEAKER_EVIDENCE_ERASURE_CHECK_ENV)
    swept = []
    found_survivor = False
    try:
        owner = data_plane.collection('users').document(uid)
        for conversation in owner.collection('conversations').list_documents():
            evidence = conversation.collection('speaker_evidence')
            delete_collection(evidence, client=data_plane)
            if verify:
                swept.append(evidence)

        for evidence in swept:
            # Firestore lists names only and fetches subsequent pages on iteration.
            for _ in evidence.list_documents():
                metrics.REMAINING.inc()
                found_survivor = True
    except Exception:
        metrics.SWEEP_FAILED.inc()
        raise

    if verify:
        metrics.SWEEP_CHECKED.inc()
        if found_survivor:
            raise RuntimeError('speaker evidence survived account erasure')
        record_checked_sweep(uid)
    else:
        metrics.SWEEP_DISABLED.inc()
