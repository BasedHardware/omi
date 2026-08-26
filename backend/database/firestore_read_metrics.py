"""Low-cardinality telemetry for Firestore reads that can amplify with user data.

The enum-backed labels deliberately rule out user identifiers, query text, and
routes. Add a family only for a reviewed, bounded set of read paths.
"""

import logging
from enum import StrEnum

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)


class FirestoreReadFamily(StrEnum):
    ACTION_ITEMS_LIST = 'action_items_list'
    ACTION_ITEMS_VISIBLE_IDS = 'action_items_visible_ids'
    LISTEN_MONTHLY_USAGE = 'listen_monthly_usage'
    ALL_TIME_USAGE = 'all_time_usage'
    CHAT_QUOTA_MONTHLY_USAGE = 'chat_quota_monthly_usage'


class FirestoreReadMode(StrEnum):
    UNBOUNDED = 'unbounded'
    BOUNDED = 'bounded'


class FirestoreReadSite(StrEnum):
    """Reviewed single-document read call sites, for NOT_FOUND attribution.

    One member per instrumented call site (see backend/database/conversations.py
    and its callers). Adding a member means a real, reviewed read path was
    wired up to pass an explicit ``read_site`` — never invent one to make a
    label "look" attributed. ``UNATTRIBUTED`` is the honest default for every
    single-document read that has not been reviewed yet.
    """

    LISTEN_CLIENT_ID_PROBE = 'listen_client_id_probe'
    LISTEN_LIFECYCLE_POLL = 'listen_lifecycle_poll'
    LISTEN_PROCESS_CONVERSATION = 'listen_process_conversation'
    LISTEN_POST_DELETE_REREAD = 'listen_post_delete_reread'
    LISTEN_RECORDING_LIFECYCLE_EVENT = 'listen_recording_lifecycle_event'
    LISTEN_TRANSCRIPT_CACHE_LOAD = 'listen_transcript_cache_load'
    LISTEN_RUNTIME_TEARDOWN = 'listen_runtime_teardown'
    LIFECYCLE_OPEN_LIVE_SESSION_BINDING = 'lifecycle_open_live_session_binding'
    PROCESS_CONVERSATION_RETRIEVE_IN_PROGRESS = 'process_conversation_retrieve_in_progress'
    FINALIZER_JOB_REPLAY = 'finalizer_job_replay'
    MEETING_RECEIPT_RECONCILER = 'meeting_receipt_reconciler'
    SYNC_PIPELINE_TARGET_CONVERSATION = 'sync_pipeline_target_conversation'
    CONVERSATIONS_VALID_BY_ID = 'conversations_valid_by_id'
    DEVELOPER_FROM_SEGMENTS_IDEMPOTENCY = 'developer_from_segments_idempotency'
    SYNC_AUDIO_URLS_POLL = 'sync_audio_urls_poll'
    CHAT_FIRST_BLOCK_VALIDATION = 'chat_first_block_validation'
    RAG_HYDRATION = 'rag_hydration'
    TRANSCRIPT_CHUNK_HYDRATION = 'transcript_chunk_hydration'
    USER_DELETION_WIPE_STATUS = 'user_deletion_wipe_status'
    UNATTRIBUTED = 'unattributed'


class FirestoreReadOutcome(StrEnum):
    HIT = 'hit'
    MISS = 'miss'


FIRESTORE_READ_OPERATIONS = Counter(
    'omi_firestore_read_operations_total',
    'Firestore reads by reviewed query family and boundedness',
    ['family', 'mode'],
)

FIRESTORE_DOCUMENTS_PER_OPERATION = Histogram(
    'omi_firestore_documents_per_operation',
    'Firestore documents iterated for a reviewed read operation',
    ['family'],
    buckets=(0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)

FIRESTORE_DOCUMENT_READS = Counter(
    'omi_firestore_document_reads_by_site_total',
    'Single-document Firestore reads by reviewed call site and whether the document existed',
    ['site', 'outcome'],
)


def record_firestore_read(
    family: FirestoreReadFamily,
    mode: FirestoreReadMode,
    documents: int,
) -> None:
    """Record one completed Firestore read without accepting dynamic labels."""
    FIRESTORE_READ_OPERATIONS.labels(family=family.value, mode=mode.value).inc()
    FIRESTORE_DOCUMENTS_PER_OPERATION.labels(family=family.value).observe(documents)


def record_document_read(site: FirestoreReadSite, outcome: FirestoreReadOutcome, count: int = 1) -> None:
    """Record one or more completed single-document Firestore reads.

    ``count`` lets a batch read (``db.get_all``) attribute many hits and
    misses from one call. This must never raise: a metrics failure must not
    break the read path it is observing, so any error is logged at warning
    and swallowed.
    """
    try:
        FIRESTORE_DOCUMENT_READS.labels(site=site.value, outcome=outcome.value).inc(count)
    except Exception:
        logger.warning('record_document_read failed site=%s outcome=%s count=%s', site, outcome, count, exc_info=True)
