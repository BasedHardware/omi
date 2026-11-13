"""Transactional document store for batch scheduling; lazy, explicitly namespaced.

Writes are buffered until the body returns so all Firestore reads precede writes.
The transaction callback must be pure; it may be retried by Firestore.
"""

from copy import deepcopy
import hashlib
import logging
import math
import os
import random
import re
import threading
import time
from typing import Any, Callable, Protocol, TypeVar

from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, Aborted

from config.batch_pipeline import contention_retry_enabled, contention_storm_damper_enabled, control_candidate_fanout
from config.firestore_read_levers import lever_enabled
from database._client import get_data_plane_firestore_client
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyMemo
from database.batch_pipeline_recovery import quarantine_fenced
from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)
from database.batch_pipeline_transaction_labels import (
    current_operation,
    pull_operation as pull_operation,
    require_operation_label,
)
from utils.sync.stage import collection_name

# Every state an obligation can drain from. Assignment needs only ``pending``;
# completion of persisted/ready rows has its own page. All share one index.
PROJECTION_DISCOVERY_STATES = ('pending', 'persisted', 'ready')
PROJECTION_OBLIGATION_STATES = (*PROJECTION_DISCOVERY_STATES, 'quarantine_held')
PROJECTION_ASSIGNMENT_STATES = ('pending',)
PROJECTION_FINISH_STATES = ('persisted', 'ready')

T = TypeVar('T')
logger = logging.getLogger(__name__)


def _finite_seconds(value: object) -> float:
    """A bounded, non-negative, finite seconds value; anything else is ``0.0``.

    The spill lanes are advisory: a hostile answer (bool, non-number,
    non-finite, zero, negative) must collapse to "no spill", never break the
    entry it was meant to space.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0.0:
        return 0.0
    return seconds


def document_ref(client: Any, namespace: str, table: str, key: str):
    """The single document address for a batch table key.

    Shared by the transactional view and the non-transactional probe so the
    two read paths cannot drift apart on table layout.
    """
    if table == 'conversations':
        uid, conversation_id = key.split('/', 1)
        return client.collection('users').document(uid).collection('conversations').document(conversation_id)
    if table == 'content':
        uid, content_id = key.split('/', 1)
        return (
            client.collection('users')
            .document(uid)
            .collection(collection_name('sync_content_ledger'))
            .document(content_id)
        )
    return client.collection(f'{namespace}_{table}').document(key)


def probe_document(client: Any, namespace: str, table: str, key: str) -> dict:
    """One strongly consistent point read outside any transaction.

    Advisory callers on hot documents gain nothing from the transactional
    ladder: a read-only body still joins a read set that aborts on every
    concurrent write to the probed document. Missing documents read as
    ``{}``, the same contract as ``Transaction.get``.
    """
    snapshot = document_ref(client, namespace, table, key).get()
    if not snapshot.exists:
        return {}
    return snapshot.to_dict() or {}


class Transaction(Protocol):
    def get(self, table: str, key: str) -> dict: ...
    def put(self, table: str, key: str, value: dict) -> None: ...
    def patch(self, table: str, key: str, fields: dict) -> None: ...
    def first_pending(self, owner_key: str) -> dict | None: ...
    def first_ready_pending(self, owner_key: str) -> dict | None: ...
    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None: ...
    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int: ...


class Store(Protocol):
    def run(self, body: Callable[[Transaction], T], *, operation: str | None = None) -> T: ...
    def probe(self, table: str, key: str) -> dict: ...
    def due(self, state: str, now: float, limit: int) -> list[str]: ...
    def oldest(self, priority: int, *, ready_only: bool) -> float | None: ...
    def oldest_retry(self, priority: int) -> float | None: ...
    def ready_for_capacity(self, priority: int, now: float) -> int: ...
    def control_candidate(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()
    ) -> str | None: ...
    def control_candidates(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
    ) -> list[str]: ...
    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool: ...
    def quarantine_fenced(self, segment_id: str, now: float) -> bool: ...
    def longest_ready_pending(self, owner_key: str) -> dict | None: ...
    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]: ...
    def head_pending(self, owner_key: str) -> dict | None: ...
    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]: ...
    def service_frontier_hint(self, priority: int) -> float: ...


class FirestoreTransaction:
    def __init__(self, client: Any, namespace: str, transaction: Any):
        self.client = client
        self.namespace = namespace
        self.transaction = transaction
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}
        # Documents outside the batch tables that join this transaction (the provider-STT outbox row).
        self.external: dict[Any, tuple[Any, dict]] = {}

    def _ref(self, table: str, key: str):
        return document_ref(self.client, self.namespace, table, key)

    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        if address not in self.cache:
            snapshot = self._ref(table, key).get(transaction=self.transaction)
            self.cache[address] = (snapshot.to_dict() or {}) if snapshot.exists else {}
        return deepcopy({**self.writes.get(address, self.cache[address]), **self.patches.get(address, {})})

    def put(self, table: str, key: str, value: dict) -> None:
        if table == 'conversations':
            raise ValueError('conversation admission requires a field patch, never a document set')
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        if table != 'conversations' or set(fields) != {'record_lane_owner'}:
            raise ValueError('only the conversation route owner may be patched by admission')
        self.patches.setdefault((table, key), {}).update(deepcopy(fields))

    def defer_set(self, ref: Any, value: dict) -> None:
        """Set a document outside the batch tables at flush, after every read of this transaction.

        Firestore refuses any transactional read after the first write, and flush itself reads
        privacy state. A joining writer that set its document on the raw transaction mid-body made
        every later read fail (ReadAfterWriteError: staging 11-01, every provider-route upload 503).
        """
        self.external[ref.path] = (ref, deepcopy(value))

    def first_pending(self, owner_key: str) -> dict | None:
        return first_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def first_ready_pending(self, owner_key: str) -> dict | None:
        return first_ready_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        queue = self.get('queues', f'{int(priority)}_{owner_key}')
        if (queue or {}).get('link_mode') == 'fifo_array':
            # The array is the FIFO's ordering authority and this transaction's
            # buffered queue writes are already visible here, so the legacy
            # ``next``-pointer index query (which reads only the snapshot and
            # misses in-transaction splices) is neither needed nor correct.
            items = queue.get('items') or []
            if segment_id not in items:
                return None
            index = items.index(segment_id)
            if index == 0:
                return None
            predecessor = self.get('jobs', items[index - 1])
            if (
                not predecessor
                or predecessor.get('state') != 'ready'
                or predecessor.get('priority') != int(priority)
                or predecessor.get('owner_key') != owner_key
            ):
                return None
            return predecessor
        return ready_predecessor(
            self.client, self.namespace, owner_key, priority, segment_id, transaction=self.transaction
        )

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        options = {}
        if lever_enabled('batch_privacy_memoize', uid):
            # FirestoreStore.run creates this view anew on every callback retry.
            if not hasattr(self, '_privacy_memo'):
                self._privacy_memo = BatchPrivacyMemo(self.client, self.transaction)
            options['memo'] = self._privacy_memo
        return assert_batch_write_allowed(
            self.client,
            self.transaction,
            uid,
            conversation_ids=conversation_ids,
            expected_generation=expected_generation,
            **options,
        )

    def flush(self):
        # Conversation patches set record_lane_owner, a batch-privacy authority
        # field, so the commit-boundary fence appends one token write per owner.
        fence_tokens = len({key.split('/', 1)[0] for table, key in self.patches if table == 'conversations'})
        if len(self.writes) + len(self.patches) + len(self.external) + fence_tokens > 450:
            raise RuntimeError('batch transaction write budget exceeded')
        guarded = set()
        for (table, key), value in self.writes.items():
            if table not in {'jobs', 'results'}:
                continue
            job = value if table == 'jobs' else self.get('jobs', key)
            identity = (job['owner_id'], job.get('conversation_id'), job.get('privacy_generation'))
            if identity in guarded:
                continue
            guarded.add(identity)
            generation = self.check_privacy(
                job['owner_id'],
                conversation_ids=(job['conversation_id'],) if job.get('conversation_id') else (),
                expected_generation=job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for (table, key), value in self.writes.items():
            self.transaction.set(self._ref(table, key), value)
        for (table, key), fields in self.patches.items():
            self.transaction.update(self._ref(table, key), fields)
        for ref, value in self.external.values():
            self.transaction.set(ref, value)


class _ContentionStormDamper:
    """Bounded per-operation re-strike spacing shared by one store instance.

    The bounded contention chain gives one operation five immediate attempts
    whose inter-attempt gaps now sum to 1.5-3.0 s (the wave-bridge cap in
    ``database/firestore_transaction_retry.py``). During a real
    contention storm every
    caller that exhausts re-strikes the same hot document at once, so the
    whole process burns its budgets in lockstep — the ``x2239/30m``
    ``operation=... outcome=exhausted`` production signature. After an
    exhaustion this damper arms a bounded, jittered residual window for that
    operation label; the next entry of the same label waits it out before
    opening another chain, while every other label keeps running untouched.
    Separately, the mid-ladder gate spaces a chain's deep rungs out of a
    wave the chain itself measured, by the same capped ladder shape and
    only once the chain's own aborts show a sustained wave (from the third
    rung), without recording anything on the shared label window: the
    first chain into a fresh storm stops exhausting inside it, and the
    exhaustion-stamped window callers schedule against stays
    exhaustion-driven.

    One store instance is one process's view of one namespace, and every
    instance of the same namespace now shares ONE damper through the
    process-level registry (``shared_storm_damper``): the scheduler shards,
    the pump, intake and maintenance all arm and consult the same per-label
    windows, so arming damps all of them, not just the caller that exhausted.
    A store that injects an explicit ``storm_damper=`` keeps its private
    damper and never joins the registry. A successful
    commit clears the ladder, but only if no concurrent arm happened since
    the entry consulted (generation guard, mirroring the pull loop's
    generation-based reset).

    The damper's reach now ends at the process boundary the same way it once
    ended at the store instance: a deployment is many pods, and the FIRST pod
    into a fresh storm measured it while every sibling pod's damper was still
    cold — five colliding attempts per pod, re-derived fleet-wide. A
    process-shared damper therefore carries an optional fleet window
    (``_FleetStormWindow``): ``arm`` broadcasts the applied window to one
    Firestore document per label, and a cold ``consult`` adopts sibling pods'
    windows, so the first exhaustion spaces the whole fleet's next entries.
    The mirror is advisory and fail-open — bounded TTL, bounded size, every
    fault collapses to "no window" — and an explicitly injected damper
    carries no fleet window, exactly as it carries no registry identity.
    """

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        fleet_window: '_FleetStormWindow | None' = None,
    ):
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._random_value = random_value
        self._fleet = fleet_window
        self._lock = threading.Lock()
        self._armed_until: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._generations: dict[str, int] = {}

    def consult(self, label: str, *, client: Any = None) -> tuple[float, int]:
        """Sleep out the residual backoff for ``label``; return ``(waited, generation)``.

        The sleep runs outside the lock so a damped entry never blocks a
        concurrent arm, consult or success. ``waited`` is ``0.0`` when no
        backoff is armed (or already expired) and no sleep happens.

        When this damper carries a fleet window, a process-local residual of
        zero is exactly the cold-start case the fleet mirror exists for: the
        sibling pods' window for ``label`` is adopted (bounded, mirrored,
        never raising) and the longer of the two residuals is slept. A
        sibling pod's exhaustion therefore spaces this process's next entry
        without this process having to burn its own chain first.
        """
        with self._lock:
            residual = self._armed_until.get(label, 0.0) - self._monotonic()
            generation = self._generations.get(label, 0)
        fleet_residual = 0.0
        if self._fleet is not None:
            fleet_residual = self._fleet.peek(label, client)
            if fleet_residual > residual:
                logger.info(
                    'event=batch_store_backoff scope=fleet operation=%s waited_ms=%d',
                    label,
                    round(fleet_residual * 1000),
                )
        wait = max(residual, fleet_residual)
        if wait <= 0.0 and self._fleet is not None:
            # Sibling-label spill: no window of our own and none for this
            # label from any pod, but the namespace has already measured a
            # storm on ANOTHER label (a sibling scheduler shard reading the
            # same hot rows). Adopt it on entry, capped by the fleet window's
            # share cap so a foreign label's deep window can never park this
            # lane for the full damper cap. Advisory and fail-open: a hostile
            # answer collapses to no spill and leaves the entry untouched.
            spill_residual = _finite_seconds(getattr(self._fleet, 'peek_spill', lambda _client: 0.0)(client))
            spill_cap = _finite_seconds(getattr(self._fleet, 'SPILL_SHARE_CAP_SECONDS', 0.0))
            if spill_cap > 0.0 and spill_residual > 0.0:
                spill_residual = min(spill_residual, spill_cap)
                logger.info('event=batch_store_backoff scope=spill waited_ms=%d', round(spill_residual * 1000))
                self._sleeper(spill_residual)
                return spill_residual, generation
        if wait <= 0.0:
            return 0.0, generation
        self._sleeper(wait)
        return wait, generation

    def peek(self, label: str, *, client: Any = None) -> tuple[float, int]:
        """Read ``(residual, generation)`` for ``label`` without sleeping.

        The mid-ladder gate reads this between a retry chain's attempts: the
        retry helper owns every pre-attempt sleep, so the damper must not
        double-sleep a wait the chain's budget has not accounted for. The
        residual never comes back negative — an expired window is ``0.0``,
        exactly like no window at all.

        Without a client the read is process-local and free, exactly as it
        has always been: no mirror read, no spill read, byte-identical to
        the pre-fleet gate.

        When this damper carries a fleet window and a client is in scope,
        the rung also adopts what the fleet has already measured, with the
        same precedence the entry consult applies: a sibling pod's armed
        window for THIS label wins over the process's own residual (it only
        ever raises the wait), and when no window exists anywhere for the
        label, the namespace spill fills in, share-capped, so a chain that
        entered before a sibling's broadcast stops re-deriving a storm the
        fleet already measured. A chain's entry consulted the same documents
        at most one mirror TTL ago, so the common chain pays zero extra
        reads; a rung past the TTL re-reads once and picks up a window a
        sibling armed mid-flight — evidence only a mid-chain read can
        deliver. Both lanes are advisory and fail-open: a hostile answer, a
        read fault, an absent or malformed document all collapse to
        "no window" and leave the bare schedule unchanged.

        Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
        """
        with self._lock:
            residual = self._armed_until.get(label, 0.0) - self._monotonic()
            generation = self._generations.get(label, 0)
        wait = max(residual, 0.0)
        if self._fleet is not None and client is not None:
            fleet_residual = self._fleet.peek(label, client)
            if fleet_residual > wait:
                logger.info(
                    'event=batch_store_backoff scope=gate_fleet operation=%s waited_ms=%d',
                    label,
                    round(fleet_residual * 1000),
                )
                wait = fleet_residual
            if wait <= 0.0:
                spill_residual = _finite_seconds(getattr(self._fleet, 'peek_spill', lambda _client: 0.0)(client))
                spill_cap = _finite_seconds(getattr(self._fleet, 'SPILL_SHARE_CAP_SECONDS', 0.0))
                if spill_cap > 0.0 and spill_residual > 0.0:
                    spill_residual = min(spill_residual, spill_cap)
                    logger.info(
                        'event=batch_store_backoff scope=gate_spill operation=%s waited_ms=%d',
                        label,
                        round(spill_residual * 1000),
                    )
                    wait = spill_residual
        return wait, generation

    def arm(self, label: str, *, client: Any = None) -> float:
        """Record one exhaustion for ``label``; return the applied retry-after seconds.

        When this damper carries a fleet window, the applied window is also
        broadcast for sibling PODS: their next entry adopts it instead of
        re-deriving the storm this process just measured. The broadcast is
        best-effort and runs OUTSIDE the damper lock — a slow or faulting
        Firestore write never delays a concurrent consult — and it never
        changes the local arithmetic or the returned seconds.
        """
        with self._lock:
            if label not in self._generations and len(self._generations) >= (
                FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS
            ):
                return 0.0  # fail-open: run undamped rather than grow state forever
            failures = self._failures.get(label, 0) + 1
            self._failures[label] = failures
            maximum = min(
                FirestoreStore.STORM_DAMPER_CAP_SECONDS,
                FirestoreStore.STORM_DAMPER_BASE_SECONDS
                * (2 ** min(failures - 1, FirestoreStore.STORM_DAMPER_LADDER_STEPS)),
            )
            delay = maximum * (0.5 + 0.5 * self._random_value())
            until = max(self._armed_until.get(label, 0.0), self._monotonic() + delay)
            self._armed_until[label] = until
            self._generations[label] = self._generations.get(label, 0) + 1
            applied = until - self._monotonic()
        if self._fleet is not None:
            # The namespace spill is broadcast FIRST so the arm's last write
            # stays the label's own window document: every grid and operator
            # surface that reads the exhaustion lane's write trail sees the
            # label document last, exactly as before the spill lane existed.
            # The spill carries this measurement to SIBLING LABELS: the
            # sharded scheduler labels contend on the same backing rows, and
            # a label with no window of its own adopts the spill on entry
            # (share-capped) instead of re-deriving the storm. Monotone and
            # best-effort like the per-label broadcast; a shallower arm never
            # lowers a deeper sibling measurement.
            self._fleet.publish_spill(label, applied, client=client)
            self._fleet.publish(label, applied, client=client)
        return applied

    def note_success(self, label: str, generation: int) -> None:
        """Clear the ladder only if no concurrent arm happened since consult."""
        with self._lock:
            if self._generations.get(label, 0) != generation:
                return
            self._armed_until.pop(label, None)
            self._failures.pop(label, None)
            self._generations.pop(label, None)

    def wave_rung_wait(self, failed_attempt: int) -> float:
        """The per-rung wait one in-chain abort spaces the next rung by.

        The same base/ladder/cap/jitter shape ``arm`` uses for a
        post-exhaustion window, indexed by the failed attempt instead of the
        label's exhaustion count, and deliberately never recorded on the
        shared state: a chain that measured a collision spaces its OWN
        remaining rungs out of the wave it is inside, while the label's
        shared window — and the exhaustion-stamped ``retry_after`` callers
        schedule against — stays exhaustion-driven.
        """
        maximum = min(
            FirestoreStore.STORM_DAMPER_CAP_SECONDS,
            FirestoreStore.STORM_DAMPER_BASE_SECONDS
            * (2 ** min(failed_attempt - 1, FirestoreStore.STORM_DAMPER_LADDER_STEPS)),
        )
        return maximum * (0.5 + 0.5 * self._random_value())

    def tracked_labels(self) -> int:
        with self._lock:
            return len(self._generations)


def fleet_storm_window_doc_id(label: str) -> str | None:
    """The storm-window document id for ``label``; ``None`` when unfit.

    Labels are the validated operation grammar (``[a-z][a-z0-9_]{0,63}`` or
    the composed serving-pull/claim form); the composed form's spaces and
    equals signs map deterministically to underscores, and the result is
    refused unless it stays inside the bounded document-id alphabet. A
    document id is an address, never an interpolation surface, and an unfit
    label fails open as "no fleet window" on both the read and the write.
    """
    doc_id = label.replace(' ', '_').replace('=', '_')
    if not re.fullmatch(r'[a-z0-9_]{1,128}', doc_id):
        return None
    return doc_id


class _FleetStormWindow:
    """Best-effort cross-process mirror of one namespace's storm windows.

    The process-shared damper made an exhaustion's re-strike window true for
    every store instance in ONE process. A deployment is not one process: a
    hot label exhausts on many pods at once, and every pod whose damper is
    still cold re-derives the storm the fleet has already measured — five
    colliding attempts per pod, exactly the ``x1056/30m`` exhausted burn the
    damper family exists to stop. This window publishes each armed window to
    one Firestore document per label (``{namespace}_storm_dampers/{doc_id}``)
    and adopts sibling pods' windows on entry, so the FIRST pod through a
    storm spaces the fleet's next entries, not just its own process.

    Everything here is advisory and fail-open: the publish is guarded by one
    bounded floor read when the mirror does not already cover the window (a
    broadcast never lowers a deeper sibling measurement) and is otherwise a
    single merge set with no SDK retry and a bounded call timeout; every
    Firestore fault
    collapses to "no fleet window", a missing or malformed document reads as
    residual ``0.0``, and per-label results are mirrored for
    ``CACHE_TTL_SECONDS`` so adoption never amplifies reads on the entry
    path. A pod that still holds a longer window of its own keeps it — the
    adopted residual only ever raises the wait to the fleet's measurement,
    never shortens the process's own. There is no separate kill switch: the
    window is carried by the process-shared damper, so it lives and dies
    with the storm damper lever the way the registry does.
    """

    # At most one storm-window read per label per process per this many
    # seconds: storms are damped by the mirror, not paid for in reads.
    CACHE_TTL_SECONDS = 1.0
    # The mirror is keyed by whatever label is consulted; labels are static
    # literals, but the bound mirrors the damper's label cap (fail-open past
    # it: the oldest mirror entry is evicted rather than growing forever).
    MAX_CACHED_LABELS = 128
    # The publish's floor read, the publish's write and the adopt each get one
    # bounded call budget; a hanging Firestore call must not extend any lane
    # the way an unbounded read would. Well above a healthy call, far below
    # the damper cap.
    CALL_TIMEOUT_SECONDS = 1.0
    # The namespace spill: one document per namespace carrying the deepest
    # window ANY label of the namespace has measured. The scheduler's pull and
    # claim labels are sharded (`batch_pull shard=scheduler_NN`) and those
    # shards contend on the same backing rows, but a storm measured on one
    # shard's label arms only that label's window — every sibling shard label
    # entered the hot rows cold and re-derived the five-attempt exhaustion the
    # fleet had already measured. The spill lane carries that measurement
    # across labels: `arm` raises the spill (never lowering a deeper one), and
    # a label whose own and fleet residuals are both zero adopts the spill on
    # entry, capped by SPILL_SHARE_CAP_SECONDS so a foreign label's deep
    # window can never park an unrelated lane for the full damper cap.
    SPILL_DOC_ID = 'namespace_storm_spill'
    SPILL_CACHE_TTL_SECONDS = 1.0
    SPILL_CALL_TIMEOUT_SECONDS = 1.0
    SPILL_SHARE_CAP_SECONDS = 1.0

    def __init__(self, namespace: str, *, wall_now: Callable[[], float] = time.time):
        self.namespace = namespace
        self._wall_now = wall_now
        self._lock = threading.Lock()
        self._until_wall: dict[str, float] = {}
        self._fetched_at: dict[str, float] = {}
        self._spill_until_wall = 0.0
        self._spill_fetched_at: float | None = None
        self._spill_label: str | None = None
        self.reads = 0
        self.absent_reads = 0
        self.malformed_reads = 0
        self.failed_reads = 0
        self.publishes = 0
        self.publish_skips = 0
        self.publish_floor_skips = 0
        self.publish_failures = 0
        self.unfit_labels = 0
        self.spill_reads = 0
        self.spill_absent_reads = 0
        self.spill_malformed_reads = 0
        self.spill_failed_reads = 0
        self.spill_publishes = 0
        self.spill_publish_skips = 0
        self.spill_publish_failures = 0
        self.spill_unfit_labels = 0

    def peek(self, label: str, client: Any = None) -> float:
        """The sibling pods' residual for ``label``; ``0.0`` without a client.

        Mirrored: at most one document read per label per
        ``CACHE_TTL_SECONDS``, and a publish warms the mirror so the
        publisher never re-reads its own window. Never raises.
        """
        if client is None:
            return 0.0
        doc_id = fleet_storm_window_doc_id(label)
        if doc_id is None:
            with self._lock:
                self.unfit_labels += 1
            return 0.0
        now = self._wall_now()
        with self._lock:
            fresh = label in self._fetched_at and now - self._fetched_at[label] < self.CACHE_TTL_SECONDS
            until_wall = self._until_wall.get(label, 0.0)
        if fresh:
            return max(0.0, until_wall - now)
        until_wall = self._fetch_until_wall(doc_id, client, now)
        self._remember(label, until_wall, now)
        return max(0.0, until_wall - now)

    def _fetch_until_wall(self, doc_id: str, client: Any, now: float) -> float:
        with self._lock:
            self.reads += 1
        try:
            snapshot = (
                client.collection(f'{self.namespace}_storm_dampers')
                .document(doc_id)
                .get(timeout=self.CALL_TIMEOUT_SECONDS)
            )
            data = snapshot.to_dict() if snapshot.exists else None
        except Exception:
            # A read fault is "no window", cached like one for the TTL: a
            # blip must degrade to process-local damping, never to retries
            # on the entry path.
            with self._lock:
                self.failed_reads += 1
            return 0.0
        if data is None:
            with self._lock:
                self.absent_reads += 1
            return 0.0
        armed_until = data.get('armed_until') if isinstance(data, dict) else None
        if (
            isinstance(armed_until, bool)
            or not isinstance(armed_until, (int, float))
            or not math.isfinite(float(armed_until))
        ):
            with self._lock:
                self.malformed_reads += 1
            return 0.0
        return float(armed_until)

    def publish(self, label: str, window_seconds: float, *, client: Any = None) -> None:
        """Broadcast one armed window for ``label``; best-effort, never raises.

        A window already covered by the mirror is skipped — during a
        lockstep burst every sibling would otherwise rewrite the same
        document with a window the first publisher already broadcast. A
        window the FLEET already covers is skipped too: when the mirror
        does not already cover the window, one bounded read refreshes the
        mirror from the live document first, and a deeper sibling window
        stands. Without that floor, a cold sibling's shallow first rung
        (or a mirror that went stale inside the TTL while a deeper window
        landed behind it) wrote straight over the storm the fleet had
        already measured, and every adopter re-entered the storm early —
        the damping collapsed to the shallowest sibling's rung exactly
        when the storm was hottest. The extra read rides the exhaustion
        lane only (publishes are proportional to exhaustions, the thing
        the damper family eliminates) and fails open exactly like an
        adopt read: a fault proceeds to the write, degrading to the
        pre-floor behavior. Both skips are advisory: they compare against
        what THIS process last saw or just fetched, and a skipped window
        costs at most the residual the mirror already carries.
        """
        if client is None:
            return
        doc_id = fleet_storm_window_doc_id(label)
        if doc_id is None:
            with self._lock:
                self.unfit_labels += 1
            return
        if not math.isfinite(float(window_seconds)) or window_seconds <= 0.0:
            return
        now = self._wall_now()
        with self._lock:
            known = self._until_wall.get(label, 0.0) - now
        if known >= float(window_seconds):
            with self._lock:
                self.publish_skips += 1
            return
        live_until = self._fetch_until_wall(doc_id, client, now)
        self._remember(label, live_until, now)
        if live_until - now >= float(window_seconds):
            with self._lock:
                self.publish_skips += 1
                self.publish_floor_skips += 1
            return
        until_wall = now + float(window_seconds)
        try:
            client.collection(f'{self.namespace}_storm_dampers').document(doc_id).set(
                {'armed_until': until_wall, 'window_seconds': float(window_seconds)},
                merge=True,
                timeout=self.CALL_TIMEOUT_SECONDS,
            )
        except Exception:
            with self._lock:
                self.publish_failures += 1
            return
        with self._lock:
            self.publishes += 1
            self._remember_locked(label, until_wall, now)

    def _remember(self, label: str, until_wall: float, now: float) -> None:
        with self._lock:
            self._remember_locked(label, until_wall, now)

    def _remember_locked(self, label: str, until_wall: float, now: float) -> None:
        if len(self._until_wall) >= self.MAX_CACHED_LABELS and label not in self._until_wall:
            oldest = min(self._fetched_at, key=lambda key: self._fetched_at[key], default=None)
            if oldest is not None:
                self._until_wall.pop(oldest, None)
                self._fetched_at.pop(oldest, None)
        self._until_wall[label] = until_wall
        self._fetched_at[label] = now

    def cached_labels(self) -> int:
        with self._lock:
            return len(self._until_wall)

    def peek_spill(self, client: Any = None) -> float:
        """The namespace's deepest live storm residual across labels; ``0.0`` without a client.

        Mirrored like the per-label window: at most one spill read per process
        per ``SPILL_CACHE_TTL_SECONDS``, and a spill publish warms the mirror
        so the arm that raised it never re-reads it. Never raises.
        """
        if client is None:
            return 0.0
        now = self._wall_now()
        with self._lock:
            fresh = self._spill_fetched_at is not None and now - self._spill_fetched_at < self.SPILL_CACHE_TTL_SECONDS
            until_wall = self._spill_until_wall
        if fresh:
            return max(0.0, until_wall - now)
        until_wall, _label = self._fetch_spill(client, now)
        self._remember_spill(_label, until_wall, now)
        return max(0.0, until_wall - now)

    def _fetch_spill(self, client: Any, now: float) -> tuple[float, str | None]:
        with self._lock:
            self.spill_reads += 1
        try:
            snapshot = (
                client.collection(f'{self.namespace}_storm_dampers')
                .document(self.SPILL_DOC_ID)
                .get(timeout=self.SPILL_CALL_TIMEOUT_SECONDS)
            )
            data = snapshot.to_dict() if snapshot.exists else None
        except Exception:
            # A read fault is "no spill", cached like one for the TTL: a blip
            # must degrade to per-label damping, never to retries on the
            # entry path.
            with self._lock:
                self.spill_failed_reads += 1
            return 0.0, None
        if data is None:
            with self._lock:
                self.spill_absent_reads += 1
            return 0.0, None
        until = data.get('armed_until') if isinstance(data, dict) else None
        label = data.get('label') if isinstance(data, dict) else None
        if isinstance(label, str) and fleet_storm_window_doc_id(label) is None:
            label = None
        if isinstance(until, bool) or not isinstance(until, (int, float)) or not math.isfinite(float(until)):
            with self._lock:
                self.spill_malformed_reads += 1
            return 0.0, None
        return float(until), label

    def _remember_spill(self, label: str | None, until_wall: float, now: float) -> None:
        with self._lock:
            self._spill_until_wall = until_wall
            self._spill_fetched_at = now
            self._spill_label = label

    def publish_spill(self, label: str, window_seconds: float, *, client: Any = None) -> None:
        """Raise the namespace spill to cover this label's window; best-effort, never raises.

        Monotone like the per-label publish floor: a live spill from ANY label
        that already reaches as deep as this window stands, and this arm
        writes nothing — during a lockstep burst across sibling labels the
        spill is written once per ladder rung the storm actually grows, not
        once per sibling arm. The stored ``label`` names whichever label last
        raised the spill; a shallower label's arm must never lower it. Every
        fault collapses to "no spill": the write is one bounded merge set with
        no SDK retry, a write fault leaves the mirror untouched, and an unfit
        label is counted and skipped on both lanes.
        """
        if client is None:
            return
        doc_id = fleet_storm_window_doc_id(label)
        if doc_id is None:
            with self._lock:
                self.spill_unfit_labels += 1
            return
        if not math.isfinite(float(window_seconds)) or window_seconds <= 0.0:
            return
        now = self._wall_now()
        until_wall = now + float(window_seconds)
        with self._lock:
            fresh = self._spill_fetched_at is not None and now - self._spill_fetched_at < self.SPILL_CACHE_TTL_SECONDS
            live_until = self._spill_until_wall
        if not fresh:
            live_until, live_label = self._fetch_spill(client, now)
            self._remember_spill(live_label, live_until, now)
        if live_until >= until_wall:
            with self._lock:
                self.spill_publish_skips += 1
            return
        try:
            client.collection(f'{self.namespace}_storm_dampers').document(self.SPILL_DOC_ID).set(
                {'armed_until': until_wall, 'label': doc_id, 'window_seconds': float(window_seconds)},
                merge=True,
                timeout=self.SPILL_CALL_TIMEOUT_SECONDS,
            )
        except Exception:
            with self._lock:
                self.spill_publish_failures += 1
            return
        with self._lock:
            self.spill_publishes += 1
        self._remember_spill(doc_id, until_wall, now)


# One damper per namespace per process, shared by every ``FirestoreStore``
# constructed without an injected ``storm_damper=``. The process mints many
# store instances for one namespace — serving, intake, provider STT, voice
# evidence and cap-hold admission each construct their own, several per call —
# and a per-instance damper made an exhaustion's re-strike window die with the
# instance that armed it: the next entry of the same label on a sibling
# instance consulted an empty damper and re-struck the hot documents at once,
# exactly the lockstep burn the damper exists to prevent. The registry makes
# the damper's contract true process-wide while staying bounded: one small
# object per namespace (prod/dev processes hold one or two; the label cap
# inside each damper still bounds its own state).
_SHARED_STORM_DAMPERS: dict[str, _ContentionStormDamper] = {}
_SHARED_STORM_DAMPERS_LOCK = threading.Lock()


def shared_storm_damper(namespace: str) -> '_ContentionStormDamper':
    """The process-shared storm damper for ``namespace``.

    Every store built without an explicit ``storm_damper=`` gets this one
    object, so an exhaustion armed through any instance spaces the next
    entry of the label on every instance of the same namespace. The damper
    carries the namespace's fleet window (``fleet_storm_window``), so its
    windows are also broadcast to and adopted from sibling PODS; the
    double-checked get-or-create is locked because stores are constructed
    on executor threads (intake admissions, serving pulls); the
    unsynchronized fast path is safe under the GIL's dict-read guarantee.

    An explicitly injected damper is honored verbatim and never registered:
    tests own their damper identity, and a foreign damper must not leak
    state into the process-shared one — or into the fleet view.

    Failure-Class: FC-storm-damper-window-dies-with-its-store-instance
    """
    damper = _SHARED_STORM_DAMPERS.get(namespace)
    if damper is None:
        with _SHARED_STORM_DAMPERS_LOCK:
            damper = _SHARED_STORM_DAMPERS.get(namespace)
            if damper is None:
                damper = _ContentionStormDamper(fleet_window=fleet_storm_window(namespace))
                _SHARED_STORM_DAMPERS[namespace] = damper
    return damper


def reset_shared_storm_dampers() -> None:
    """Drop every process-shared damper.

    Test-isolation seam: a test that arms a label through one store must not
    leak that window into the next test's stores of the same namespace. The
    unit conftest resets the registry around every test; production code
    never calls this — the process-shared windows are the feature.
    """
    with _SHARED_STORM_DAMPERS_LOCK:
        _SHARED_STORM_DAMPERS.clear()


# The fleet mirror registry, keyed like the damper registry: one mirror per
# namespace per process, created alongside its damper by
# ``shared_storm_damper`` so every store of the namespace publishes into and
# adopts from the same cross-process view. Bounded by the namespace count,
# exactly like the damper registry.
_FLEET_STORM_WINDOWS: dict[str, _FleetStormWindow] = {}
_FLEET_STORM_WINDOWS_LOCK = threading.Lock()


def fleet_storm_window(namespace: str) -> _FleetStormWindow:
    """The process-level fleet window for ``namespace``.

    The double-checked get-or-create mirrors ``shared_storm_damper``: stores
    are constructed on executor threads, and two concurrent constructions of
    one namespace must observe the same mirror.
    """
    window = _FLEET_STORM_WINDOWS.get(namespace)
    if window is None:
        with _FLEET_STORM_WINDOWS_LOCK:
            window = _FLEET_STORM_WINDOWS.get(namespace)
            if window is None:
                window = _FleetStormWindow(namespace)
                _FLEET_STORM_WINDOWS[namespace] = window
    return window


def reset_fleet_storm_windows() -> None:
    """Drop every fleet window; the test-isolation twin of the damper reset.

    A mirror entry is a wall-clock window another test's fake client wrote;
    carrying it across tests would let one test's storm leak into the next
    test's adopt. Production code never calls this — the mirrors are the
    feature.
    """
    with _FLEET_STORM_WINDOWS_LOCK:
        _FLEET_STORM_WINDOWS.clear()


def batch_lane_storm_damper(namespace: str) -> '_ContentionStormDamper | None':
    """The namespace's process storm damper, or ``None`` while a switch is off.

    The non-store batch lanes — the privacy fence, the lease revocations, the
    quarantine-recovery cancel and the voice-evidence receipts — write the
    same hot ``control``/``jobs``/``results``/``owners``/``artifacts`` rows
    the store labels storm on, so their joins resolve the ONE shared damper
    per namespace (or per fence partition) through this per-call resolver.
    Both kill switches read per call exactly like the store's
    ``contention_storm_damper`` property, so a dormant damper is ``None``
    and the lane below stays byte-for-byte the bare ladder. Lanes import
    this lazily: this module sits above them in the database graph.
    """
    if not (contention_retry_enabled() and contention_storm_damper_enabled()):
        return None
    return shared_storm_damper(namespace)


def run_batch_pipeline_transaction(
    client: Any,
    operation: Callable[[Any], Any],
    *,
    operation_name: str,
    storm_damper: Any = None,
    logger: Any = None,
) -> Any:
    """Run one batch-pipeline transaction with the namespace's bounded retries.

    A bare ``operation(client.transaction())`` hands contention to the SDK's
    same-id commit loop: one transaction id replayed inside the armed storm
    window, retrying into the exact collision the store lane's damper has
    already measured, with an expiry retirement the SDK never retries and an
    exhaustion that surfaces as an anonymous fault with no label and no
    window. Aborted and expired transactions write nothing, and the body
    rereads every document, so a fresh transaction replays it safely.

    The chain joins the process storm damper exactly like the store,
    projection, retention, pump, purge and scheduler lanes: the entry consult
    sleeps out the label's residual window (fleet-adopted, spill share-capped)
    before the first attempt — the first attempt itself is never gated — every
    rung after a measured collision re-peeks the residual and, from the third
    failed rung on, spaces itself by the same capped wave ladder, an
    exhaustion arms the label and stamps the applied window onto
    ``retry_after``, and a commit clears the ladder only when no concurrent
    arm bumped the generation. With ``storm_damper`` ``None`` the schedule is
    the bare bounded ladder: five fresh transactions, equal-jitter rungs,
    nothing recorded. ``logger`` keeps each lane's backoff lines under the
    lane's own module logger; the store lane is the default.

    Failure-Class: FC-bare-batch-pipeline-lanes-collide-inside-armed-storm-window
    """
    from database._client import run_transactional
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        run_with_transaction_contention_retry,
    )

    lane_logger = logger if logger is not None else logging.getLogger(__name__)
    label = operation_name
    latest_generation = 0

    def mid_ladder_gate(failed_attempt: int) -> float:
        nonlocal latest_generation
        if storm_damper is None:
            return 0.0
        residual, gate_generation = storm_damper.peek(label, client=client)
        latest_generation = gate_generation
        wait = residual
        if failed_attempt >= FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT:
            wait = max(residual, storm_damper.wave_rung_wait(failed_attempt))
        if wait <= 0.0:
            return 0.0
        lane_logger.info(
            'event=%s_backoff scope=mid_ladder operation=%s attempt=%d waited_ms=%d',
            label,
            label,
            failed_attempt,
            round(wait * 1000),
        )
        return wait

    if storm_damper is not None:
        waited, generation = storm_damper.consult(label, client=client)
        if waited > 0:
            lane_logger.info(
                'event=%s_backoff operation=%s waited_ms=%d',
                label,
                label,
                round(waited * 1000),
            )
        latest_generation = generation

    try:
        result = run_with_transaction_contention_retry(
            # One SDK commit attempt per transaction: the outer helper is the only
            # commit-contention budget (5 bodies, not 5 x 5).
            lambda: client.transaction(max_attempts=1),
            lambda transaction: run_transactional(client, operation, initial_transaction=transaction),
            operation_name=operation_name,
            inter_attempt_gate=mid_ladder_gate,
        )
    except FirestoreContentionExhausted as error:
        # This label just burned its whole budget against the hot rows:
        # space out the next re-strike instead of colliding immediately,
        # and carry the applied window for the caller's own schedule.
        if storm_damper is not None:
            error.retry_after = storm_damper.arm(label, client=client)
        raise
    if storm_damper is not None:
        storm_damper.note_success(label, latest_generation)
    return result


class FirestoreStore:
    # Storm-damper ladder shape. Delays mirror the worker pull loop's damper
    # (exponential ladder under an equal jitter) but cap well below the pull
    # loop's 30s ceiling: a store entry is on the record-latency path, so the
    # damper trades at most a few seconds of wait for skipping a doomed
    # immediate collision with the same hot documents.
    STORM_DAMPER_BASE_SECONDS = 0.25
    STORM_DAMPER_CAP_SECONDS = 4.0
    STORM_DAMPER_LADDER_STEPS = 4
    # Operation labels are static literals, but nothing in the label grammar
    # bounds how many distinct ones a process can mint; stop damping new
    # labels beyond this (fail-open) instead of growing state forever.
    STORM_DAMPER_MAX_TRACKED_LABELS = 64
    # The mid-ladder wave wait engages from this failed attempt onward: two
    # measured collisions on one chain are sustained-wave evidence. The early
    # rungs keep their sub-second transient-collision recovery, and the
    # default chain's first two rungs stay byte-identical to the bare ladder.
    WAVE_ENGAGEMENT_ATTEMPT = 3

    def __init__(
        self, namespace: str, *, firestore_client: Any = None, storm_damper: '_ContentionStormDamper | None' = None
    ):
        # Require a stage-qualified name; never infer dev from the customer project.
        if namespace not in {'batch_pipeline_prod', 'batch_pipeline_dev'} and not re.fullmatch(
            r'batch_pipeline_test_[a-z0-9_]{1,40}', namespace
        ):
            raise ValueError('explicit batch_pipeline_{prod,dev,test_<id>} namespace required')
        self.namespace = namespace
        self._client = firestore_client
        self._require_stage()
        # One process-shared damper per namespace: an exhaustion armed through
        # any instance must space the next entry of that label on every
        # instance, and the process mints many instances for one namespace —
        # serving, intake, provider STT, voice evidence and cap-hold admission
        # each construct their own, several per call. A per-instance damper
        # let that window die with its store, so siblings re-struck the hot
        # documents at once. An injected damper stays private to this store.
        #
        # Failure-Class: FC-storm-damper-window-dies-with-its-store-instance
        self._storm_damper = storm_damper if storm_damper is not None else shared_storm_damper(namespace)

    @property
    def contention_storm_damper(self) -> '_ContentionStormDamper | None':
        """The namespace's storm damper, or ``None`` while a contention switch is off.

        The projection lane (``ProjectionStore.run``) reads this to consult
        the same per-label windows every batch-store entry arms: a storm one
        lane measured on the shared ``jobs``/``results`` rows must space
        every lane that writes those rows, not only the lane that exhausted.
        Resolved per call exactly like ``run`` resolves it, so both kill
        switches stay live and a dormant damper is ``None``, never consulted.
        """
        if not (contention_retry_enabled() and contention_storm_damper_enabled()):
            return None
        return self._storm_damper

    def _require_stage(self):
        if self.namespace.startswith('batch_pipeline_test_'):
            host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
            if not host.startswith(('127.0.0.1:', 'localhost:')):
                raise RuntimeError('test namespace requires a loopback emulator; no cloud fallback')
            if self._client is not None and getattr(self._client, '_emulator_host', None) != host:
                raise RuntimeError('injected test client must be bound to the loopback emulator')
        else:
            stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
            if stage not in {'prod', 'dev'} or self.namespace != f'batch_pipeline_{stage}':
                raise RuntimeError('batch namespace must match explicit runtime stage')

    @property
    def client(self):
        self._require_stage()
        return self._client if self._client is not None else get_data_plane_firestore_client()

    def run(self, body, *, operation: str | None = None):
        """One lease-fenced batch transaction under a static caller label.

        The label resolves from the explicit ``operation=`` or the ambient
        ``store_operation`` context; with neither, the call is refused before
        any client is touched. The anonymous ``batch_pipeline_store`` default
        let dozens of unrelated call sites blend into one unattributable
        ``outcome=exhausted`` storm.

        Under the retry ladder the store's storm damper also applies: an
        exhausted label arms a bounded, jittered re-strike window and the
        next entry of that same label waits it out (logged at INFO as
        ``event=batch_store_backoff``), while every other label runs
        untouched. The damper is dormant when either contention kill switch
        is off.

        The damper also spaces the chain's OWN remaining rungs: between two
        attempts of one chain, a sibling's exhaustion may have armed the
        label's window mid-flight, and re-striking the hot document inside
        that window burns every remaining rung against a collision the damper
        has already measured. Each retry rung therefore re-reads the label's
        residual through a non-sleeping damper peek — fleet-aware now, so a
        rung also adopts a window a sibling pod armed mid-flight and, on a
        cold label, the namespace spill share-capped, exactly like the entry
        consult — and adds it to the rung's
        equal-jitter wait (logged at INFO as
        ``event=batch_store_backoff scope=mid_ladder``). From the third rung
        — two measured collisions, sustained-wave evidence — the chain's
        rung also spaces itself by the same capped ladder the damper arms
        after an exhaustion, indexed by the failed attempt and never
        recorded on the shared state, so the first chain into a fresh storm
        lands its deep rungs after the wave instead of exhausting inside
        it. The first attempt is never gated — a chain that reached the
        transaction always gets one try — the early rungs keep their
        sub-second transient-collision recovery, and with the damper
        dormant the schedule is byte-for-byte the bare ladder. A success
        clears the ladder only if no arm happened since the latest consult
        or mid-ladder peek (generation guard).

        The window the damper keeps is fleet-shared: the process-shared
        damper carries the namespace's fleet mirror, so this entry adopts
        sibling pods' armed windows on entry (logged at INFO as
        ``event=batch_store_backoff scope=fleet`` when the fleet's window
        outwaits the process's own) and this process's exhaustions broadcast
        theirs. A cold pod waits out a storm the fleet already measured
        instead of re-deriving it with a fresh five-attempt chain; both the
        adopt and the broadcast are best-effort, and every fault collapses
        to the process-local behavior. An injected ``storm_damper=`` carries
        no fleet mirror, exactly as it carries no registry identity.

        Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
        """
        label = require_operation_label(operation if operation is not None else current_operation())
        client = self.client
        damper = self._storm_damper if (contention_retry_enabled() and contention_storm_damper_enabled()) else None
        generation = 0
        if damper is not None:
            waited, generation = damper.consult(label, client=client)
            if waited > 0:
                logger.info('event=batch_store_backoff operation=%s waited_ms=%d', label, round(waited * 1000))
        # The latest damper generation this entry has observed: the entry
        # consult's, refreshed by every mid-ladder peek, so a sibling arming
        # the window mid-chain still holds the success-clearing guard honest.
        latest_generation = generation

        def mid_ladder_gate(failed_attempt: int) -> float:
            nonlocal latest_generation
            if damper is None:
                return 0.0
            residual, gate_generation = damper.peek(label, client=client)
            latest_generation = gate_generation
            # This chain's own aborts are storm evidence. The gate never used
            # to wait for anything unless a sibling had already exhausted:
            # the FIRST chain into a fresh storm had no window to wait out
            # and spent its whole budget colliding inside the wave it was
            # itself measuring. From the third rung — two measured
            # collisions, sustained-wave evidence — the rung also spaces
            # itself by the same capped ladder the damper arms after an
            # exhaustion, indexed by the failed attempt and never recorded
            # on the shared state, so exhaustion stamping stays
            # exhaustion-driven. The early rungs keep their sub-second
            # transient-collision recovery; a sibling's armed window still
            # wins whenever it is longer. The residual itself is fleet-aware
            # now: a rung past the entry consult's mirror TTL re-reads the
            # label's window document once and adopts a window a sibling pod
            # armed mid-flight (logged as scope=gate_fleet), and a cold
            # label adopts the namespace spill share-capped
            # (scope=gate_spill) — a chain that entered before the broadcast
            # no longer re-derives a storm the fleet already measured.
            #
            # Failure-Class: FC-storm-window-arms-only-after-exhaustion
            wait = residual
            if failed_attempt >= FirestoreStore.WAVE_ENGAGEMENT_ATTEMPT:
                wait = max(residual, damper.wave_rung_wait(failed_attempt))
            if wait <= 0.0:
                return 0.0
            logger.info(
                'event=batch_store_backoff scope=mid_ladder operation=%s attempt=%d waited_ms=%d',
                label,
                failed_attempt,
                round(wait * 1000),
            )
            return wait

        client = self.client

        @firestore.transactional
        def commit(transaction):
            view = FirestoreTransaction(client, self.namespace, transaction)
            result = body(view)
            view.flush()
            return result

        if not contention_retry_enabled():
            return commit(client.transaction())
        # The outer budget owns fresh transaction IDs and all retries. The
        # SDK's same-ID commit loop would multiply the contention window.
        try:
            result = run_with_transaction_contention_retry(
                lambda: client.transaction(max_attempts=1),
                commit,
                operation_name=label,
                inter_attempt_gate=mid_ladder_gate,
            )
        except FirestoreContentionExhausted as error:
            # This label just burned its whole budget against hot documents;
            # space out the next re-strike instead of colliding immediately.
            # The window the damper actually applied rides on the exception:
            # a caller that schedules its own re-offer (the pump's deferred
            # drain lane) lands it after the armed window instead of
            # colliding inside it on a fixed ladder.
            if damper is not None:
                error.retry_after = damper.arm(label, client=client)
            raise
        if damper is not None:
            damper.note_success(label, latest_generation)
        return result

    def probe(self, table: str, key: str) -> dict:
        """Strongly consistent single-document read outside any transaction.

        Advisory only: every decision that writes still re-verifies its
        fences inside the ``run`` transaction that acts on the document.
        """
        return probe_document(self.client, self.namespace, table, key)

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return due(self.client, self.namespace, state, now, limit)

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        return oldest(self.client, self.namespace, priority, ready_only=ready_only)

    def ready_for_capacity(self, priority: int, now: float) -> int:
        return ready_for_capacity(self.client, self.namespace, priority, now)

    def oldest_admissible_ready(self, priority: int, now: float) -> float | None:
        return oldest_admissible_ready(self.client, self.namespace, priority, now)

    def control_candidate(self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()) -> str | None:
        return control_candidate(self.client, self.namespace, priority, pool, now, worker_id=worker_id, exclude=exclude)

    def control_candidates(
        self, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
    ) -> list[str]:
        return control_candidates(self.client, self.namespace, priority, pool, now, worker_id=worker_id, fanout=fanout)

    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool:
        # One conditional write, no transaction or retrying read set. A stale
        # hint can only lose the CAS, never authorize two simultaneous owners.
        with pull_operation('claim', shard):
            ref = self.client.collection(f'{self.namespace}_pull_claims').document(shard)
            snapshot = ref.get()
            if (snapshot.to_dict() or {}).get('expires_at', 0) > now:
                return False
            value = {'token': token, 'expires_at': now + ttl}
            try:
                if snapshot.exists:
                    ref.update(value, option=firestore.LastUpdateOption(snapshot.update_time), retry=None)
                else:
                    ref.create(value, retry=None)
            except (AlreadyExists, FailedPrecondition, Aborted):
                logger.info('event=batch_shard_contention operation=batch_claim shard=%s outcome=busy', shard)
                return False
            return True

    def oldest_retry(self, priority: int) -> float | None:
        return oldest_retry(self.client, self.namespace, priority)

    def service_frontier_hint(self, priority: int) -> float:
        # Advisory probe twin of the retired transactional frontier read: the
        # rejoin fairness seed is read outside any transaction so an admission
        # body never joins the argmax shard's abort set
        # (utils/batch_pipeline/control.activate).
        return service_frontier_hint(self.client, self.namespace, priority)

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        return quarantine_fenced(self.client, self.namespace, segment_id, now)

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # A hint read outside any transaction; the bypass transaction re-verifies it.
        return longest_ready_pending(self.client, self.namespace, owner_key)

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        # A hint read outside any transaction; the fresh-first transaction re-verifies it.
        return fresh_pending(self.client, self.namespace, owner_key, limit)

    def head_pending(self, owner_key: str) -> dict | None:
        # A hint read outside any transaction; the merge commit re-verifies its candidate.
        return head_pending(self.client, self.namespace, owner_key)

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        return held_merge_owners(self.client, self.namespace, limit, after=after)

    def projection_pending(self, limit: int = 100) -> list[str]:
        return projection_pending(self.client, self.namespace, limit)

    def projection_page(
        self, limit: int = 100, *, after=None, states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES
    ) -> tuple[list[str], Any]:
        return projection_page(self.client, self.namespace, limit, after=after, states=states)

    def projection_successor(self, owner_key: str, previous: str | None) -> str | None:
        return projection_successor(self.client, self.namespace, owner_key, previous)


def projection_pending(client: Any, namespace: str, limit: int = 100) -> list[str]:
    return projection_page(client, namespace, limit)[0]


def projection_page(
    client: Any,
    namespace: str,
    limit: int = 100,
    *,
    after=None,
    states: tuple[str, ...] = PROJECTION_DISCOVERY_STATES,
) -> tuple[list[str], Any]:
    """Stable keyset page; the cursor survives removal of its source row.

    __name__ breaks committed_at ties (including siblings committed together).
    Cursor values are discovery hints, never authorization or ordering fences.
    ``states`` narrows the same ``in`` filter to a subset of the drain states.
    """
    if not states or not set(states) <= set(PROJECTION_OBLIGATION_STATES):
        raise ValueError('projection discovery states must be drain states')
    collection = client.collection(f'{namespace}_results')
    query = collection.where('projection_state', 'in', list(states)).order_by('committed_at').order_by('__name__')
    if after is not None:
        query = query.start_after({'committed_at': after[0], '__name__': collection.document(after[1])})
    size = max(1, min(limit, 100))
    docs = list(query.limit(size).stream())
    # Wrap even when blocked rows remain. Rows inserted behind the cursor are
    # revisited on the next cycle; no durable obligation is skipped or mutated.
    cursor = (docs[-1].to_dict()['committed_at'], docs[-1].id) if len(docs) == size else None
    return [doc.id for doc in docs], cursor


def projection_successor(client: Any, namespace: str, owner_key: str, previous: str | None) -> str | None:
    """The owner's result committed directly after ``previous`` in its log.

    The result log is a per-owner singly linked list; two matches fail closed.
    A discovery hint only: the transactional predecessor check still decides.
    """
    docs = list(
        client.collection(f'{namespace}_results')
        .where('owner_key', '==', owner_key)
        .where('previous_segment_id', '==', previous)
        .order_by('__name__')
        .limit(2)
        .stream()
    )
    return docs[0].id if len(docs) == 1 else None


def first_pending(client: Any, namespace: str, owner_key: str, *, transaction: Any = None) -> dict | None:
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if docs else None


def head_pending(client: Any, namespace: str, owner_key: str) -> dict | None:
    """The owner's earliest-captured pending row, read outside any transaction.

    Non-transactional discovery hint for the merge gate: a blocked-head drain
    decides from this read that no transaction can commit instead of joining
    the hot head row's abort set. The acting transaction always re-verifies
    its candidate.
    """
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream()
    )
    return docs[0].to_dict() if docs else None


def first_ready_pending(client: Any, namespace: str, owner_key: str, *, transaction: Any = None) -> dict | None:
    """The owner's earliest-captured pending row that already has a result (bounded head wait)."""
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('state', '==', 'result_ready')
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if docs else None


def longest_ready_pending(client: Any, namespace: str, owner_key: str) -> dict | None:
    """The owner's pending result that has waited longest; rows without ``ready_at`` never match.

    Non-transactional discovery hint: it takes no transactional query lock.
    """
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('state', '==', 'result_ready')
        .order_by('ready_at')
        .limit(1)
        .stream()
    )
    return docs[0].to_dict() if docs else None


def held_merge_owners(
    client: Any, namespace: str, limit: int, *, after: str | None = None
) -> list[tuple[str, str | None]]:
    """Owners whose catch-up commits are held for projection depth: (owner key, owner id or None).

    Ordered by owner key after ``after`` so callers can rotate through every
    marker. The marker stores no user ID; the owner's earliest pending job
    supplies it. None means nothing is pending, so the marker is stale.
    """
    collection = client.collection(f'{namespace}_merge_holds')
    query = collection.where('held', '==', True).order_by('__name__')
    if after is not None:
        query = query.start_after({'__name__': collection.document(after)})
    marks = query.limit(max(1, min(limit, 100))).stream()
    owners = []
    for mark in marks:
        job = first_pending(client, namespace, mark.id)
        owners.append((mark.id, job.get('owner_id') if job else None))
    return owners


def fresh_pending(client: Any, namespace: str, owner_key: str, limit: int) -> list[dict]:
    """The owner's earliest-captured pending fresh rows, ready or not (fresh-first merge).

    Non-transactional discovery hint: it takes no transactional query lock.
    """
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .where('fresh_capture', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(max(1, min(limit, 32)))
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def ready_predecessor(
    client: Any, namespace: str, owner_key: str, priority: int, segment_id: str, *, transaction: Any = None
) -> dict | None:
    # Leased/completed rows retain stale next links. Only a ready row in this
    # owner's priority FIFO can be the live predecessor. Two matches fail closed.
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .where('next', '==', segment_id)
        .order_by('__name__')
        .limit(2)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if len(docs) == 1 else None


def due(client: Any, namespace: str, state: str, now: float, limit: int = 100) -> list[str]:
    if state not in {'leased', 'retry', 'result_ready', 'record_pending'}:
        raise ValueError('only recoverable states may be scanned')
    field = {
        'leased': 'lease_until',
        'retry': 'available_at',
        'result_ready': 'enqueued_at',
        'record_pending': 'available_at',
    }[state]
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('state', '==', state)
        .where(field, '<=', now)
        .order_by(field)
        .limit(max(1, min(limit, 500 if state == 'record_pending' else 100)))
        .stream()
    )
    return [doc.id for doc in docs]


# Bounded FIFO prefix walked past policy holds and dispositioned rows. An
# exempt prefix with a sentinel exports NaN: an unmeasured commitment may sit
# beyond the bound. The observer and pager report that incomplete scan as
# blindness; retiring holds themselves stays with the custody track.
OLDEST_POLICY_HOLD_SCAN_LIMIT = 500


def is_allowance_policy_hold(job: dict[str, Any]) -> bool:
    """A durable end-of-allowance hold parks the obligation outside compute.

    scheduler.defer records the decision on the job document; an
    allowance_exhausted hold is a policy parking state, not a compute
    commitment, so age-based safety proxies must not measure it (2026-10-25:
    131 such holds, ~26h old, kept the in-cluster guard's
    uncommitted_job_age_over_30m proxy tripped permanently and masked real
    wedges). An unevaluated re-evaluation clears the decision to BLIND without
    ending the hold; until an allow or another hold replaces it, the job's
    last_policy_hold still classifies it (2026-10-27: held jobs re-read as
    decisionless between evaluations flapped the proxy to ~54h).
    """
    decision = job.get('compute_decision')
    if not decision:
        return (job.get('last_policy_hold') or {}).get('reason') == 'allowance_exhausted'
    return decision.get('outcome') == 'held' and decision.get('reason') == 'allowance_exhausted'


def is_policy_hold(job: dict[str, Any], now: float | None = None) -> bool:
    """A parked obligation the uncommitted-age proxy must not measure: an allowance hold, or a live
    ``vendor_held`` provider unit (vendor_route_contracts.is_vendor_policy_hold). A vendor hold
    whose redrive is overdue past the stale grace is measured again, so a dead redrive surfaces.
    """
    if is_allowance_policy_hold(job):
        return True
    if job.get('state') != 'vendor_held':
        return False
    from config.batch_pipeline_vendor_failover import held_redrive_seconds, held_stale_grace_seconds
    from utils.batch_pipeline.vendor_route_contracts import is_vendor_policy_hold

    return is_vendor_policy_hold(
        job,
        time.time() if now is None else now,
        redrive_seconds=held_redrive_seconds(),
        stale_grace_seconds=held_stale_grace_seconds(),
    )


def ready_for_capacity(client: Any, namespace: str, priority: int, now: float) -> int:
    """Count work awaiting a first/re-authorized attempt, never held legacy debt.

    New admission explicitly records unattempted; existing workers already
    replace it with allowed/held or clear it on an unevaluated refusal. Reusing
    that authoritative state avoids a new eligibility bit that old workers
    would fail to clear during a mixed-version roll. Unmarked legacy jobs remain
    durable/drainable but cannot buy GPUs. This hint never grants paid compute.
    """
    query = (
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .where('merge_pending', '==', True)
        .where('compute_decision.outcome', 'in', ['unattempted', 'allowed'])
        .where('available_at', '<=', now)
    )
    count = query.count().get()[0][0].value
    # The pinned SDK decodes integer_value=0 through ``integer or double``,
    # yielding 0.0. Preserve that real empty result; do not coerce missing,
    # fractional, negative or otherwise malformed responses into capacity.
    if type(count) is float and count == 0.0:
        count = 0
    if type(count) is not int or count < 0:
        raise ValueError('nonnegative integer capacity count required')
    return count


# Bounded ready prefix the vendor-overflow backlog read walks (route selection, one read per
# refresh in the healthy case). Policy holds and deferred rows at the head are skipped.
ADMISSIBLE_READY_SCAN_LIMIT = 20


def is_admissible_ready(job: dict[str, Any], now: float) -> bool:
    """The ``ready_for_capacity`` predicate on one ready row: work a GPU would run if it had a lane."""
    decision = job.get('compute_decision')
    available_at = job.get('available_at')
    return (
        job.get('merge_pending') is True
        and isinstance(decision, dict)
        and decision.get('outcome') in ('unattempted', 'allowed')
        and isinstance(available_at, (int, float))
        and available_at <= now
        and not is_policy_hold(job, now)
    )


def oldest_admissible_ready(client: Any, namespace: str, priority: int, now: float) -> float | None:
    """Enqueue time of the oldest admissible ready unit, or None when the bounded prefix has none.

    Same index as ``oldest(ready_only=True)``. A due allowance hold back in ``ready`` carries an
    hours-old enqueue time, so it is skipped rather than read as GPU backlog. A prefix made only of
    skipped rows reads as no backlog: overflow then fails toward GPU, which is today's routing.
    """
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('state', '==', 'ready')
        .order_by('enqueued_at')
        .limit(ADMISSIBLE_READY_SCAN_LIMIT)
        .stream()
    )
    for doc in docs:
        job = doc.to_dict()
        if is_admissible_ready(job, now):
            return job['enqueued_at']
    return None


def oldest(client: Any, namespace: str, priority: int, *, ready_only: bool = False) -> float | None:
    query = client.collection(f'{namespace}_jobs').where('priority', '==', priority)
    if ready_only:
        docs = list(query.where('state', '==', 'ready').order_by('enqueued_at').limit(1).stream())
        return docs[0].to_dict()['enqueued_at'] if docs else None
    # The uncommitted-age proxy must measure the oldest real commitment: walk a
    # bounded prefix of the FIFO and skip allowance and vendor policy holds. Early return
    # keeps the healthy case a one-document read; a sentinel row beyond the
    # bound (limit + 1) distinguishes truncation from a FIFO that happens to be
    # exactly as long as the bound.
    docs = iter(
        query.where('merge_pending', '==', True)
        .order_by('enqueued_at')
        .limit(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)
        .stream()
    )
    scanned = 0
    for doc in docs:
        scanned += 1
        if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT:
            break  # the sentinel row exists: the scan was truncated
        job = doc.to_dict()
        if is_queue_dispositioned(job) or is_policy_hold(job):
            continue
        return job['enqueued_at']
    if scanned > OLDEST_POLICY_HOLD_SCAN_LIMIT:
        # An unmeasured commitment may exist beyond the bound. NaN is an
        # incomplete measurement, never a hold misreported as late work or a
        # false fresh zero. The guard and alert route treat this as blindness.
        return float('nan')
    return None


def control_candidate(
    client: Any, namespace: str, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()
) -> str | None:
    candidates = control_candidates(client, namespace, priority, pool, now, worker_id=worker_id)
    return next((key for key in candidates if key not in exclude), None)


def control_candidates(
    client: Any, namespace: str, priority: int, pool: str, now: float, *, worker_id: str = '', fanout: int | None = None
) -> list[str]:
    if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
        raise ValueError('bounded priority and pool required')
    prefix = f'p{priority}_'
    service, available = prefix + 'service', prefix + pool + '_available_at'
    docs = list(
        client.collection(f'{namespace}_control')
        .where(prefix + 'active', '==', True)
        .where(service, '>=', 0)
        .where(available, '<=', now)
        .order_by(service)
        .order_by(available)
        .limit(control_candidate_fanout(fanout) if worker_id else 1)
        .stream()
    )
    if worker_id:
        # Service remains the primary fairness key. Only equal-service shards
        # use worker affinity, and a busy shard can be skipped without writes.
        docs.sort(key=lambda doc: (doc.to_dict()[service], hashlib.sha256(f'{worker_id}:{doc.id}'.encode()).digest()))
    return [doc.id for doc in docs]


def is_queue_dispositioned(job: dict[str, Any]) -> bool:
    """Custody has left the compute queue; recovery/projection have their own alarms.

    A completed terminal marker alone is insufficient: result_ready still owes
    its ordered commit. Unknown states remain measured, so schema drift fails closed.
    """
    return job.get('state') in {'dead', 'quarantined', 'committed', 'privacy_blocked'}


def oldest_retry(client: Any, namespace: str, priority: int) -> float | None:
    docs = iter(
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('retry_started_at', '>=', 0)
        .order_by('retry_started_at')
        .limit(OLDEST_POLICY_HOLD_SCAN_LIMIT + 1)
        .stream()
    )
    for index, doc in enumerate(docs):
        if index == OLDEST_POLICY_HOLD_SCAN_LIMIT:
            return float('nan')
        job = doc.to_dict()
        if not is_queue_dispositioned(job) and not is_policy_hold(job):
            return job['retry_started_at']
    return None


# 2-hour timeliness alarm (David, 2026-11-02). Indexes: jobs (state, enqueued_at), the capacity index, jobs
# (priority, retry_started_at), jobs (state, recovery_state, enqueued_at) and results (projection_state, committed_at).
TIMELINESS_ACTIVE_STATES = ('leased', 'result_ready')
TIMELINESS_UNCOMMITTED_STATES = (*TIMELINESS_ACTIVE_STATES, 'ready', 'retry', 'vendor_held')
TIMELINESS_HOLD_SCAN_LIMIT = 20
TIMELINESS_PROJECTION_SCAN_LIMIT = 50


def is_timeliness_hold(job: dict[str, Any], now: float) -> bool:
    """A deliberate admission refusal (allowance, budget, fair use, daily ceiling) or a live vendor hold."""
    return is_policy_hold(job, now) or (job.get('compute_decision') or {}).get('outcome') == 'held'


def is_terminal_empty(job: dict[str, Any]) -> bool:
    """Settled empty_asr, failed held, with no recoverable speech: measured held VAD speech exactly 0."""
    return (
        job.get('state') == 'quarantined'
        and job.get('recovery_state') == 'failed_held'
        and ((job.get('recovery') or {}).get('failure') or {}).get('reason') == 'empty_asr'
        and job.get('measured_held_vad_speech_seconds') == 0
    )


def timeliness_sample(
    client: Any, namespace: str, epoch: float, now: float, sla: float, *, terminal_empty_processed: bool = False
) -> dict[str, Any]:
    """Unpublished units by wait leg: oldest ``enqueued_at`` at or after ``epoch``, counts past ``sla`` for the
    new cohort, and backlog counts before ``epoch``.

    ``terminal_empty`` is always counted. With ``terminal_empty_processed`` those units leave the quarantined
    leg: its count subtracts them exactly, so a page of them can hide a younger unit but never a breach.

    Holds must never fill a bound: ``ready`` is read through the capacity index with the decision filtered in
    the query, admission holds park in ``retry`` without ``retry_started_at`` (compute-failure retries are read
    by that field), and live ``vendor_held`` units are walked apart from active work. Results carry no enqueue
    time, so the projection leg reads the jobs behind its oldest committed rows; its counts clock from
    ``committed_at``, a lower bound. ``truncated`` names a leg whose bounded prefix may hide an older unit.
    """
    jobs = client.collection(f'{namespace}_jobs')
    results = client.collection(f'{namespace}_results')
    due = now - sla

    def first(query, field):
        docs = list(query.order_by(field).limit(1).stream())
        return docs[0].to_dict()[field] if docs else None

    def count(query):
        return int(query.count().get()[0][0].value)

    def walk(query, field):
        docs = [doc.to_dict() for doc in query.order_by(field).limit(TIMELINESS_HOLD_SCAN_LIMIT).stream()]
        admitted = [
            job['enqueued_at'] for job in docs if job['enqueued_at'] >= epoch and not is_timeliness_hold(job, now)
        ]
        full = len(docs) == TIMELINESS_HOLD_SCAN_LIMIT
        # Ordered by admission, the first unheld row is the oldest. Ordered by any other clock, a full page
        # may hide an older admission behind it.
        return min(admitted, default=None), full and (not admitted or field != 'enqueued_at')

    def committed_walk(query):
        rows = list(
            query.where('committed_at', '>=', epoch)
            .order_by('committed_at')
            .limit(TIMELINESS_PROJECTION_SCAN_LIMIT)
            .stream()
        )
        refs = [jobs.document(row.id) for row in rows]
        admitted = [
            started
            for snapshot in (client.get_all(refs, field_paths=['enqueued_at']) if refs else [])
            for started in [(snapshot.to_dict() or {}).get('enqueued_at')]
            if isinstance(started, (int, float)) and started >= epoch
        ]
        return min(admitted, default=None), len(rows) == TIMELINESS_PROJECTION_SCAN_LIMIT

    walks = [
        walk(
            jobs.where('state', 'in', list(TIMELINESS_ACTIVE_STATES)).where('enqueued_at', '>=', epoch), 'enqueued_at'
        ),
        walk(jobs.where('state', '==', 'vendor_held').where('enqueued_at', '>=', epoch), 'enqueued_at'),
    ]
    for priority in (0, 1, 2):
        ready = (
            jobs.where('priority', '==', priority)
            .where('state', '==', 'ready')
            .where('merge_pending', '==', True)
            .where('compute_decision.outcome', 'in', ['unattempted', 'allowed'])
            .where('available_at', '>=', epoch)
        )
        walks.append(walk(ready, 'available_at'))
        walks.append(
            walk(jobs.where('priority', '==', priority).where('retry_started_at', '>=', epoch), 'retry_started_at')
        )
    projection = results.where('projection_state', 'in', list(PROJECTION_DISCOVERY_STATES))
    projected, projection_truncated = committed_walk(projection)
    quarantined = jobs.where('state', '==', 'quarantined')
    legs = {
        'quarantined': (quarantined, 'enqueued_at'),
        # A quarantined projection receipt holds its committed job in the same transaction: the text never
        # reached the conversation.
        'assignment_held': (
            jobs.where('state', '==', 'committed').where('recovery_state', '==', 'held'),
            'enqueued_at',
        ),
        'projection': (projection, 'committed_at'),
        # Ready receipts already in the conversation plus assignment holds; only the ledger waits. Visible only.
        'quarantine_held_rows': (results.where('projection_state', '==', 'quarantine_held'), 'committed_at'),
        # A subset of quarantined, matching is_terminal_empty. Visible only.
        'terminal_empty': (
            quarantined.where('recovery_state', '==', 'failed_held')
            .where('recovery.failure.reason', '==', 'empty_asr')
            .where('measured_held_vad_speech_seconds', '==', 0),
            'enqueued_at',
        ),
    }
    over_sla = {
        leg: count(query.where(field, '>=', epoch).where(field, '<', due)) if due > epoch else 0
        for leg, (query, field) in legs.items()
    }
    if terminal_empty_processed:
        over_sla['quarantined'] -= over_sla['terminal_empty']
        docs = [
            doc.to_dict()
            for doc in quarantined.where('enqueued_at', '>=', epoch)
            .order_by('enqueued_at')
            .limit(TIMELINESS_HOLD_SCAN_LIMIT)
            .stream()
        ]
        kept = [job['enqueued_at'] for job in docs if not is_terminal_empty(job)]
        # Past a full page of exempt rows the exact count still names a breach, and the last row bounds its age.
        quarantined_oldest = kept[0] if kept else docs[-1]['enqueued_at'] if over_sla['quarantined'] and docs else None
    else:
        quarantined_oldest = first(quarantined.where('enqueued_at', '>=', epoch), 'enqueued_at')
    return {
        'new_oldest': {
            'uncommitted': min((started for started, _ in walks if started is not None), default=None),
            'quarantined': quarantined_oldest,
            'assignment_held': first(legs['assignment_held'][0].where('enqueued_at', '>=', epoch), 'enqueued_at'),
            'projection': projected,
            'quarantine_held_rows': first(
                legs['quarantine_held_rows'][0].where('committed_at', '>=', epoch), 'committed_at'
            ),
        },
        'new_over_sla': over_sla,
        'backlog': {
            'uncommitted_incl_holds': count(
                jobs.where('state', 'in', list(TIMELINESS_UNCOMMITTED_STATES)).where('enqueued_at', '<', epoch)
            ),
            **{leg: count(query.where(field, '<', epoch)) for leg, (query, field) in legs.items()},
        },
        'truncated': {
            'uncommitted': any(truncated for _, truncated in walks),
            'projection': projection_truncated,
        },
    }


def service_frontier_hint(client: Any, namespace: str, priority: int) -> float:
    """The fleet's highest committed virtual service for ``priority``, read outside any transaction.

    Advisory probe: the rejoin fairness seed. The max-service control document
    is the hottest shard under load — every fairness scan of the winning shard
    rewrites it — so a transaction that reads it joins that abort set for a
    purely advisory value. Reading the seed as a hint trades a bounded fairness
    transient for never joining the hottest abort set; it authorizes nothing.
    """
    if priority not in (0, 1, 2):
        raise ValueError('bounded priority required')
    name = f'p{priority}_service'
    docs = list(
        client.collection(f'{namespace}_control').order_by(name, direction=firestore.Query.DESCENDING).limit(1).stream()
    )
    return docs[0].to_dict()[name] if docs else 0.0
