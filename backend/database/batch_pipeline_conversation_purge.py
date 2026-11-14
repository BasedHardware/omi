"""Resumable, bounded erasure of one tombstoned conversation's batch-pipeline rows.

``purge_batch_owner`` is one uninterrupted pass: it links artifacts and intakes
to the conversation through segment ids it holds in memory, after it has
already erased the jobs/results that carry that link. Interrupt it (a legal
hold, a deadline, a crash) between the two and a rerun can no longer find
those dependents. This pass keeps every dependent reachable:

1. ``discover``  read-only: every matching job/result segment id is persisted
   (content-free) through the run's progress before anything is erased;
2. ``dependents`` artifacts, projections, intakes and shadow jobs that match
   the conversation or a persisted segment are erased;
3. ``parked``    owner-id fallback artifacts, matched the same way;
4. ``segments``  each persisted segment's job/result, the conversation binding,
   is erased last and its record removed only after;
5. ``shadow``    the jobstore shadow purge, only in shadow mode.

Every destructive step runs in a short unit (``UNIT_MAX_ROWS`` rows or
``UNIT_BUDGET_SECONDS``) inside ``progress.unit()``, which owns the account
gate and re-validates run ownership. The scan position is checkpointed after
each page, so a run can hand off before its task deadline and resume past a
long unmatched prefix.
"""

from __future__ import annotations

import time
from typing import Any, Callable, ContextManager, Iterable, Protocol

from google.cloud import firestore

from database import rpc_deadline
from database._client import get_data_plane_firestore_client
from database import batch_pipeline_privacy_queries as queries
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_purge import NAMESPACES
from database.batch_pipeline_purge import delete_job as _delete_job
from database.batch_pipeline_purge import erase_artifact as _erase_artifact
from database.batch_pipeline_purge import erase_result as _erase_result
from database.batch_pipeline_purge import row_belongs as _belongs
from database.batch_pipeline_purge import row_references as _references
from database.batch_pipeline_shadow_hook import mirror_refresh, purge_owner as purge_jobstore_owner
from database.batch_pipeline_shadow_hook import shadow_mode_enabled as _shadow_mode
from database.legal_holds import settles_unknown_erasure

PHASES = ('discover', 'dependents', 'parked', 'segments', 'shadow')
DISCOVER_TABLES = ('jobs', 'results')
DEPENDENT_TABLES = (
    'artifacts',
    'projections',
    'intakes',
    'shadow_jobs',
    'coalesce_groups',
    'coalesce_sources',
    'coalesce_heads',
)
# A unit stops starting rows at either bound; each row is a few bounded RPCs.
UNIT_MAX_ROWS = 10
UNIT_BUDGET_SECONDS = 1.5
SEGMENT_PAGE = 20
# Storage RPCs inside a unit are bounded so one hung call cannot pin the account gate.
OBJECT_DELETE_TIMEOUT_SECONDS = 5.0


class PurgeCheckpointed(Exception):
    """The run budget ran out at a checkpoint; the next run resumes from it."""


class Progress(Protocol):
    position: dict[str, Any]

    def checkpoint(self, position: dict[str, Any], *, add_segments: tuple[str, Iterable[str]] | None = None) -> None:
        """Persist position (and newly found segments) under run ownership."""
        ...

    def segments(self, namespace: str) -> set[str]:
        """Every persisted segment id for ``namespace``."""
        ...

    def pending_segments(self, namespace: str, limit: int) -> list[str]:
        """Persisted segment ids not yet erased."""
        ...

    def segments_done(self, namespace: str, segment_ids: Iterable[str]) -> None:
        """Remove erased segment records under run ownership."""
        ...

    def unit(self) -> ContextManager[Any]:
        """One destructive unit: account gate + ownership check; yields its ``UnitAuthority``."""
        ...

    def settle_stuck(self, resolve: Callable[[str], bool]) -> None:
        """Settle a gate left held by an unknown remote outcome before taking a new one."""
        ...

    def expired(self) -> bool:
        """Whether this run must hand off at the next checkpoint."""
        ...


def _cursor(client: Any, namespace: str, table: str, after: str | None) -> Any:
    # Name-ordered cursor that stays valid after the row it names was erased.
    if not after:
        return None
    return firestore.DocumentSnapshot(
        client.collection(f'{namespace}_{table}').document(after), {}, True, None, None, None
    )


def _ensure_budget(progress: Progress) -> None:
    """No unit or read batch starts past the run budget; resume replays from the last checkpoint."""
    if progress.expired():
        raise PurgeCheckpointed()


def _in_transaction(client: Any, body: Callable[[Any], Any]) -> Any:
    @firestore.transactional
    def run(transaction):
        return body(transaction)

    return run(client.transaction())


def _fenced_delete(client: Any, reference: Any, fence: Callable[[Any], None]) -> None:
    def body(transaction):
        fence(transaction)  # the erasing transaction itself re-proves authority
        transaction.delete(reference)

    _in_transaction(client, body)


def _in_units(
    progress: Progress,
    rows: list[Any],
    erase: Callable[[Any, Any], None],
    clock: Callable[[], float],
    settle: Callable[[], None],
) -> int:
    pending = list(rows)
    erased = 0
    while pending:
        _ensure_budget(progress)
        settle()
        with progress.unit() as authority:
            started = clock()
            done = 0
            while (
                pending
                and done < UNIT_MAX_ROWS
                and (done == 0 or (clock() - started < UNIT_BUDGET_SECONDS and not progress.expired()))
            ):
                erase(pending.pop(0), authority)
                done += 1
            erased += done
    return erased


def purge_conversation(
    uid: str,
    conversation_id: str,
    progress: Progress,
    *,
    firestore_client: Any = None,
    delete_uri: Callable[[str, str], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Erase ``conversation_id``'s batch rows from ``progress.position`` onward; returns rows erased."""
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    rpc_deadline.bind_firestore_client(client)  # erasures inside units honour the unit deadline
    tombstone = client.collection('users').document(uid).collection('deleted_conversations').document(conversation_id)
    if not tombstone.get().exists:
        raise RuntimeError('conversation deletion intent required before batch purge')
    if delete_uri is None:
        from utils.batch_pipeline.retention import delete_batch_object
        from utils.other.local_storage import create_storage_client

        # One client per run, built outside any unit when possible; its session honours the unit deadline.
        storage: list[Any] = []
        try:
            storage.append(rpc_deadline.bind_storage_client(create_storage_client()))
        except Exception:  # noqa: BLE001 - e.g. no storage configured here; build on first use
            pass

        def bounded_delete(owner: str, uri: str) -> None:
            if not storage:
                storage.append(rpc_deadline.bind_storage_client(create_storage_client()))
            delete_batch_object(owner, uri, timeout=OBJECT_DELETE_TIMEOUT_SECONDS, storage_client=storage[0])

        delete_uri = bounded_delete
    key = privacy_owner_key(uid)
    start = dict(progress.position or {})
    start_ns = int(start.get('ns') or 0)
    erased = 0

    def mark(position: dict[str, Any], **kwargs: Any) -> None:
        progress.checkpoint(position, **kwargs)
        if progress.expired():
            raise PurgeCheckpointed()

    def remote_delete(authority: Any) -> Callable[[str, str], None]:
        # Every object delete holds the gate until its outcome is known (UnitAuthority.remote).
        def delete(owner: str, uri: str) -> None:
            authority.remote(lambda: delete_uri(owner, uri), target=uri)

        return delete

    def resolve(target: str) -> bool:
        # Settles a stuck gate only on proof the targeted generation is gone (never on a 503).
        return settles_unknown_erasure(lambda: delete_uri(uid, target))

    def settle() -> None:
        progress.settle_stuck(resolve)

    def erase_dependent(namespace: str, table: str) -> Callable[[Any, Any], None]:
        def erase(item: Any, authority: Any) -> None:
            snapshot, data = item
            if table == 'artifacts':
                _erase_artifact(
                    uid, namespace, snapshot, data, remote_delete(authority), fence=authority.fence, client=client
                )
                return
            if table == 'coalesce_groups':
                from database.batch_pipeline_coalescing import purge_group

                purge_group(client, namespace, snapshot.id, uid, fence=authority.fence)
                return
            for uri in _references(data):
                remote_delete(authority)(uid, uri)
            _fenced_delete(client, snapshot.reference, authority.fence)
            mirror_refresh(namespace, [(table, snapshot.id)])

        return erase

    for ns_index in range(start_ns, len(NAMESPACES)):
        namespace = NAMESPACES[ns_index]
        resuming = ns_index == start_ns and start.get('phase') in PHASES
        first_phase = PHASES.index(start['phase']) if resuming else 0
        for phase_index in range(first_phase, len(PHASES)):
            phase = PHASES[phase_index]
            here = resuming and phase_index == first_phase
            first_table = int(start.get('table') or 0) if here else 0
            after = start.get('after') if here else None
            if phase in ('discover', 'dependents'):
                tables = DISCOVER_TABLES if phase == 'discover' else DEPENDENT_TABLES
                segments = progress.segments(namespace) if phase == 'dependents' else set()
                for table_index in range(first_table, len(tables)):
                    table = tables[table_index]
                    cursor = after if table_index == first_table else None
                    while True:
                        _ensure_budget(progress)
                        rows = queries.owner_documents(
                            client, namespace, table, key, after=_cursor(client, namespace, table, cursor)
                        )
                        if not rows:
                            break
                        cursor = rows[-1].id
                        position = {'ns': ns_index, 'phase': phase, 'table': table_index, 'after': cursor}
                        if phase == 'discover':
                            found = []
                            for snapshot in rows:
                                data = snapshot.to_dict() or {}
                                result = {}
                                if table == 'jobs':
                                    # Unsaved page: an expiry here replays it from the previous cursor.
                                    _ensure_budget(progress)
                                    result_ref = client.collection(f'{namespace}_results').document(snapshot.id)
                                    result = result_ref.get().to_dict() or {}
                                projection = result.get('projection') or data.get('projection')
                                if _belongs({**data, 'projection': projection}, conversation_id):
                                    found.append(snapshot.id)
                            mark(position, add_segments=(namespace, found))
                            continue
                        matches = []
                        for snapshot in rows:
                            data = snapshot.to_dict() or {}
                            if (
                                _belongs(data, conversation_id)
                                or (table == 'artifacts' and data.get('segment_id') in segments)
                                or (table == 'intakes' and segments.intersection(data.get('segment_ids') or []))
                            ):
                                matches.append((snapshot, data))
                        erased += _in_units(progress, matches, erase_dependent(namespace, table), clock, settle)
                        mark(position)
                    mark({'ns': ns_index, 'phase': phase, 'table': table_index + 1, 'after': None})
            elif phase == 'parked':
                segments = progress.segments(namespace)
                cursor = after
                while True:
                    _ensure_budget(progress)
                    rows = queries.artifacts_by_owner_id(
                        client, namespace, uid, after=_cursor(client, namespace, 'artifacts', cursor)
                    )
                    if not rows:
                        break
                    cursor = rows[-1].id
                    matches = []
                    for snapshot in rows:
                        data = snapshot.to_dict() or {}
                        if data.get('owner_key') == key:
                            continue  # Already handled in ``dependents``, including pending writes.
                        if _belongs(data, conversation_id) or data.get('segment_id') in segments:
                            matches.append((snapshot, data))
                    erased += _in_units(progress, matches, erase_dependent(namespace, 'artifacts'), clock, settle)
                    mark({'ns': ns_index, 'phase': phase, 'table': 0, 'after': cursor})
            elif phase == 'segments':
                while True:
                    _ensure_budget(progress)
                    pending = progress.pending_segments(namespace, SEGMENT_PAGE)
                    if not pending:
                        break
                    for chunk_start in range(0, len(pending), UNIT_MAX_ROWS):
                        chunk = pending[chunk_start : chunk_start + UNIT_MAX_ROWS]
                        bindings = []
                        for segment_id in chunk:
                            # Each read is its own batch: none starts past the budget.
                            _ensure_budget(progress)
                            job = client.collection(f'{namespace}_jobs').document(segment_id).get()
                            _ensure_budget(progress)
                            result = client.collection(f'{namespace}_results').document(segment_id).get()
                            bindings.append((segment_id, job, result))
                        done: list[str] = []

                        def erase_binding(
                            item: Any, authority: Any, namespace: str = namespace, done: list[str] = done
                        ) -> None:
                            segment_id, job, result = item
                            result_data = (result.to_dict() or {}) if result.exists else {}
                            if job.exists:
                                for uri in _references(job.to_dict() or {}) | _references(result_data):
                                    remote_delete(authority)(uid, uri)
                                _delete_job(client, namespace, job, retain_ordering=True, fence=authority.fence)
                            elif result_data and result_data.get('projection_state') != 'erased':
                                for uri in _references(result_data):
                                    remote_delete(authority)(uid, uri)
                                _erase_result(client, namespace, result, fence=authority.fence)
                                mirror_refresh(namespace, [('results', segment_id)])
                            done.append(segment_id)

                        _ensure_budget(progress)
                        settle()
                        with progress.unit() as authority:
                            started = clock()
                            for item in bindings:
                                if done and (clock() - started >= UNIT_BUDGET_SECONDS or progress.expired()):
                                    break
                                erase_binding(item, authority)
                            # Records go only after their binding is gone, under the same ownership.
                            progress.segments_done(namespace, done)
                        erased += len(done)
                        if len(done) < len(bindings):
                            break  # Budget hit; re-read pending (the rest stays recorded).
                    mark({'ns': ns_index, 'phase': phase, 'table': 0, 'after': None})
            elif phase == 'shadow' and _shadow_mode():
                _ensure_budget(progress)
                settle()
                with progress.unit():
                    purge_jobstore_owner(namespace, uid)
            if phase_index + 1 < len(PHASES):
                mark({'ns': ns_index, 'phase': PHASES[phase_index + 1]})
            else:
                # Past the last namespace this resumes to an empty loop, i.e. complete.
                mark({'ns': ns_index + 1, 'phase': PHASES[0]})
        start = {}
    return erased


__all__ = ['PHASES', 'PurgeCheckpointed', 'purge_conversation']
