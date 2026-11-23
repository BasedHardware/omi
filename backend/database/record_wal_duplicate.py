"""Read-only replay and a compare-and-set for native duplicate uploads."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from prometheus_client import Counter

from config.record_audio import record_identity
from config.record_wal_duplicate import MAX_JOBS, MERGE_TARGET_FIELD, RECEIPT_FIELD, SETTLED_FIELD, SOURCE_FIELD
from database import record_wal_handoff as handoff
from database.batch_pipeline_artifact_missing import artifact_missing
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_reads import read_snapshot, write_snapshot
from database.sync_ledger import LEDGER_RETENTION_DAYS, is_valid_completed_sync_content_result
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit

MAX_FILES = 20
MAX_VIEW_READS = 5 + 3 + MAX_JOBS + 2 * MAX_FILES
MAX_REDIRECT_READS = 4
lifecycle_rpcs = Counter(
    'omi_record_wal_handoff_duplicate_firestore_transactions_total',
    'Duplicate WAL snapshot lifecycle RPC attempts and outcomes',
    ['mode', 'rpc', 'outcome'],
)


@dataclass
class PointReads:
    work: ArtifactReadBudget
    limit: int = MAX_VIEW_READS
    issued: int = 0
    mode: str = 'settle'

    def transaction_rpc(self, rpc, outcome):
        # Observe at the leaf. If the async request is cancelled, the bounded
        # worker still accounts for the actual RPC outcome and cleanup.
        lifecycle_rpcs.labels(self.mode, rpc, outcome).inc()

    @property
    def deadline(self):
        return self.work.deadline

    def timeout(self, ceiling):
        return self.work.timeout(ceiling)

    def point(self, ceiling):
        if self.issued >= self.limit:
            raise ArtifactReadLimit('duplicate WAL point-read limit')
        timeout = self.work.timeout(ceiling)
        self.issued += 1
        return timeout


@dataclass
class AuthorityReads:
    reads: PointReads
    limit: int = 5
    issued: int = 0

    def timeout(self, ceiling):
        if self.issued >= self.limit:
            raise ArtifactReadLimit('duplicate WAL owner-read limit')
        self.issued += 1
        return self.reads.point(ceiling)


@dataclass(frozen=True)
class Request:
    uid: str
    cid: str
    source: str
    device: str
    content_id: str
    recording_session: str | None
    claim_digest: str | None


@dataclass(frozen=True)
class ProofScope:
    generation: int
    source_digest: str
    source: dict


@dataclass
class View:
    scope: ProofScope
    file_ids: tuple[str, ...]
    known: dict[str, dict]
    reply: dict
    prior: dict | None
    marked: bool


def _read(view, reads, request, files, expected):
    uid, cid = request.uid, request.cid
    replay = files is None
    generation, protection, row = handoff.check_owner_authority(
        view.client,
        view.transaction,
        uid,
        cid,
        request.source,
        request.device,
        expected.generation if expected else None,
        sampling_read_budget=AuthorityReads(reads, 5 + MAX_REDIRECT_READS if replay else 5),
        allow_retained_merge=replay,
    )
    if (
        row.get('status') != 'completed'
        and not (
            replay and row.get('status') == 'merging' and row.get(SETTLED_FIELD) is True and row.get('merge_job_id')
        )
        or row.get('record_audio_closed') is not True
        or not row.get('finished_at')
        or row.get('record_audio_partial')
        or row.get('record_upload_failed')
        or row.get('record_audio_removal_pending')
        and not (replay and row.get(MERGE_TARGET_FIELD))
        or row.get('record_upload_sessions')
        or row.get('record_wal_handoff_present')
        or request.recording_session is not None
        and (row.get('external_data') or {}).get('recording_session_id') != request.recording_session
    ):
        return None
    record, _ = record_identity(uid, cid)
    job = 'bp_' + record
    prior = view.get('content', f'{uid}/{request.content_id}')
    stored = prior.get(RECEIPT_FIELD) if prior else None
    if prior and not isinstance(stored, dict):
        return None
    if stored:
        if request.claim_digest is not None and stored.get('claim_digest') != request.claim_digest:
            return None
        ids = stored.get('file_ids')
        if not isinstance(ids, list) or not 0 < len(ids) <= MAX_FILES:
            return None
        file_ids = tuple(ids)
    elif files:
        file_ids = tuple(handoff.file_identity(uid, cid, generation, entry) for entry in files)
    else:
        return None
    if len(set(file_ids)) != len(file_ids) or any(
        type(key) is not str or len(key) != 64 or any(ch not in '0123456789abcdef' for ch in key) for key in file_ids
    ):
        return None
    if files and file_ids != tuple(handoff.file_identity(uid, cid, generation, entry) for entry in files):
        return None

    canonical = view.get('content', f'{uid}/{record}')
    intake = view.get('intakes', job)
    attestation = intake.get(SOURCE_FIELD)
    if (
        not isinstance(attestation, dict)
        or intake.get('owner_id') != uid
        or intake.get('conversation_id') != cid
        or intake.get('content_id') != record
        or intake.get('coalesce_group')
        or canonical.get('job_id') != job
        or canonical.get('dispatch_protocol') != 'batch_v1'
        or attestation.get('revision') != row.get('record_upload_revision')
    ):
        return None
    segments = intake.get('segment_ids')
    if not isinstance(segments, list) or not 0 < len(segments) <= MAX_JOBS or segments != attestation.get('units'):
        return None
    source_digest = handoff.identity([job, generation, protection, attestation, row['finished_at'].isoformat()])
    if expected and source_digest != expected.source_digest:
        return None
    if stored and (
        stored.get('scope') != source_digest
        or stored.get('privacy_generation') != generation
        or prior.get('job_id') != job
        or prior.get('record_content_id') != record
    ):
        return None
    reply = _completed_status(view, request, canonical, intake, job, segments, generation)
    if reply is None:
        return None
    known = {}
    for file_id in file_ids:
        if view.get('intakes', 'wal_file_' + file_id):
            return None
        receipt = view.get('intakes', 'wal_duplicate_' + file_id)
        if receipt:
            if (
                receipt.get('kind') != RECEIPT_FIELD
                or receipt.get('owner_id') != uid
                or receipt.get('conversation_id') != cid
                or receipt.get('privacy_generation') != generation
                or receipt.get('scope') != source_digest
            ):
                return None
            known[file_id] = receipt
    if stored and len(known) != len(file_ids):
        return None
    return View(
        ProofScope(generation, source_digest, attestation),
        file_ids,
        known,
        reply,
        prior or None,
        row.get(SETTLED_FIELD) is True,
    )


def _completed_status(view, request, canonical, intake, job, segments, generation):
    # Initially settle only completed, single-target native records. Polling
    # helper durable_status can re-drive held work and is never used here.
    result = canonical.get('result')
    if (
        canonical.get('status') != 'completed'
        or not is_valid_completed_sync_content_result(result)
        or set([*(result.get('new_memories') or []), *(result.get('updated_memories') or [])]) - {request.cid}
        or result['total_segments'] != len(segments)
    ):
        return None
    for segment in segments:
        unit = view.get('jobs', segment)
        if (
            unit.get('state') != 'committed'
            or unit.get('owner_id') != request.uid
            or unit.get('conversation_id') != request.cid
            or unit.get('capture_source_conversation_id') not in {None, request.cid}
            or unit.get('privacy_generation') != generation
            or artifact_missing(unit)
        ):
            return None
    return {
        'job_id': job,
        'status': 'completed',
        'total_files': intake['total_files'],
        'total_segments': len(segments),
        'poll_after_ms': 0,
        'lane': intake['lane'],
    }


def reconcile(store, reads, request, *, files=None, expected=None, placements=None, commit=False):
    """Return a qualified view or atomically settle an already proved view."""

    def read(view):
        state = _read(view, reads, request, files, expected)
        if state is None or placements is None:
            return state
        if expected is None or len(placements) != len(state.file_ids):
            return None
        for file_id, placement in zip(state.file_ids, placements):
            if file_id in state.known and state.known[file_id].get('placement') != placement:
                return None
        if state.prior or not commit:
            return state
        for file_id, placement in zip(state.file_ids, placements):
            if file_id not in state.known:
                view.put(
                    'intakes',
                    'wal_duplicate_' + file_id,
                    {
                        'kind': RECEIPT_FIELD,
                        'owner_id': request.uid,
                        'owner_key': privacy_owner_key(request.uid),
                        'conversation_id': request.cid,
                        'privacy_generation': state.scope.generation,
                        'scope': state.scope.source_digest,
                        'placement': placement,
                        'segment_ids': [],
                    },
                )
        if not state.marked:
            view.transaction.update(
                view.client.collection('users').document(request.uid).collection('conversations').document(request.cid),
                {SETTLED_FIELD: True},
            )
        record, _ = record_identity(request.uid, request.cid)
        view.put(
            'content',
            f'{request.uid}/{request.content_id}',
            {
                'record_content_id': record,
                'job_id': state.reply['job_id'],
                'dispatch_protocol': 'batch_v1',
                'conversation_ids': [request.cid],
                RECEIPT_FIELD: {
                    'scope': state.scope.source_digest,
                    'privacy_generation': state.scope.generation,
                    'file_ids': list(state.file_ids),
                    'claim_digest': request.claim_digest,
                },
                'expires_at': datetime.now(timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS),
            },
        )
        return state

    runner = write_snapshot if commit else read_snapshot
    return runner(store, read, reads, on_rpc=reads.transaction_rpc)
