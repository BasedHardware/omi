"""One backend matrix for the job-store conformance suites (plan A0, cross-plan L4).

``store_backend`` is a parametrized pytest fixture over ``sim``, ``emulator`` and ``postgres``. It
yields a :class:`StoreHarness` that exposes the batch ``Store`` plus the synthetic customer-data
authority (the privacy fence reads accounts, conversations and the privacy generation from
Firestore-shaped documents on every backend).

A backend whose infrastructure is missing is SKIPPED, because a laptop without a Firestore emulator
must still run the rest. A skip proves nothing, so ``OMI_REQUIRE_STORE_BACKENDS=emulator,postgres``
(comma list or ``all``) turns a missing backend into a failure; run it that way when a result is
claimed. GitHub CI has no Postgres service (it needs a ``.github`` change that has not been named,
swarm S6), so the ``postgres`` parameter skips there by design and is proven locally and on staging.

Postgres discovery order, all loopback by construction (a unix socket in a private temp dir):
1. ``OMI_TEST_POSTGRES_DSN`` for an already-running server. A non-local host additionally needs
   ``OMI_TEST_POSTGRES_ALLOW_REMOTE=1`` (staging); tests only ever touch ``batch_pipeline_test_*``
   namespaces, but migrations do create the schema.
2. ``initdb``/``postgres`` on PATH or under a Postgres install directory.
3. The ``pgserver`` wheel's bundled PostgreSQL.
"""

from __future__ import annotations

import atexit
import glob
import importlib.util
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

BACKENDS = ('sim', 'emulator', 'postgres')
_BATCH_TABLES = ('jobs', 'queues', 'owners', 'control', 'results', 'gpus', 'intakes', 'artifacts')


class BackendUnavailable(Exception):
    pass


def required_backends() -> set[str]:
    raw = os.getenv('OMI_REQUIRE_STORE_BACKENDS', '').strip().lower()
    if raw == 'all':
        return set(BACKENDS)
    return {part.strip() for part in raw.split(',') if part.strip()}


# -- customer-data authority (privacy fence inputs) -------------------------------------------------
class ClientCustomerData:
    """The same synthetic customer documents `testing.pipeline_sim.store.CustomerData` writes, over a
    real Firestore client (the emulator). Method names mirror CustomerData."""

    def __init__(self, client: Any):
        self.client = client

    def _doc(self, *path: str):
        ref: Any = self.client
        for index, part in enumerate(path):
            ref = ref.collection(part) if index % 2 == 0 else ref.document(part)
        return ref

    def add_user(self, uid: str, *, protection: str = 'standard') -> None:
        self._doc('users', uid).set({'data_protection_level': protection, 'private_cloud_sync_enabled': True})

    def add_conversation(self, uid: str, conversation_id: str) -> None:
        self._doc('users', uid, 'conversations', conversation_id).set({'status': 'completed'})

    def merge_conversation(self, uid: str, source_id: str, target_id: str) -> None:
        self.add_conversation(uid, target_id)
        self._doc('users', uid, 'conversations', source_id).set({'deleted': True, 'sync_merged_into': target_id})

    def delete_conversation(self, uid: str, conversation_id: str) -> None:
        self._doc('users', uid, 'deleted_conversations', conversation_id).set({'deleted': True})

    def block_privacy(self, uid: str) -> None:
        from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key

        ref = self._doc(PRIVACY_COLLECTION, privacy_owner_key(uid))
        previous = ref.get().to_dict() or {}
        ref.set({'generation': int(previous.get('generation', 0)) + 1, 'blocked': True, 'purging': True})

    def delete_account(self, uid: str) -> None:
        self._doc('account_deletions', uid).set({'wipe_status': 'pending'})

    def blocked(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> bool:
        from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

        try:
            assert_batch_write_allowed(
                self.client,
                None,  # plain reads: an unstarted transaction cannot serve API requests
                uid,
                conversation_ids=tuple(conversation_ids),
                expected_generation=expected_generation,
            )
        except BatchPrivacyBlocked:
            return True
        return False


@dataclass
class StoreHarness:
    name: str
    store: Any
    customer: Any
    namespace: str
    uid_suffix: str
    cleanup_steps: list[Callable[[], None]] = field(default_factory=list)

    def uid(self, label: str) -> str:
        """A uid unique to this harness, so a shared emulator or database never mixes runs."""
        return f'{label}-{self.uid_suffix}'

    def seed_user(self, label: str, **kwargs) -> str:
        uid = self.uid(label)
        self.customer.add_user(uid, **kwargs)
        return uid

    def close(self) -> None:
        for step in reversed(self.cleanup_steps):
            step()


# -- local Postgres -------------------------------------------------------------------------------------
def _find_postgres_bin() -> Path | None:
    for root in (
        os.getenv('OMI_TEST_POSTGRES_BIN'),
        *glob.glob('/opt/homebrew/opt/postgresql@1[6-9]/bin'),
        *glob.glob('/usr/lib/postgresql/1[6-9]/bin'),
    ):
        if root and (Path(root) / 'initdb').exists():
            return Path(root)
    initdb = shutil.which('initdb')
    if initdb:
        return Path(initdb).parent
    try:
        import pgserver
    except ImportError:
        return None
    bundled = Path(pgserver.__file__).parent / 'pginstall' / 'bin'
    return bundled if (bundled / 'initdb').exists() else None


class LocalPostgres:
    """A throwaway cluster on a private unix socket. Never listens on a TCP port."""

    def __init__(self, bin_dir: Path):
        self.bin = bin_dir
        self.root = Path(tempfile.mkdtemp(prefix='omi-jobstore-pg-', dir=os.getenv('OMI_TEST_PG_ROOT') or None))
        self.data = self.root / 'data'
        self.socket_dir = self.root / 's'
        self.socket_dir.mkdir()
        # Unix socket paths are length limited (~100 bytes); fail early with a clear message.
        if len(str(self.socket_dir)) > 80:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = Path(tempfile.mkdtemp(prefix='ojs-', dir='/tmp'))
            self.data = self.root / 'data'
            self.socket_dir = self.root / 's'
            self.socket_dir.mkdir()
        self.port = str(self._free_port())  # unix socket file name only; listen_addresses is empty
        subprocess.run(
            [str(self.bin / 'initdb'), '-D', str(self.data), '-U', 'postgres', '--auth=trust', '-E', 'UTF8'],
            check=True,
            capture_output=True,
            timeout=120,
        )
        options = f"-c listen_addresses='' -c unix_socket_directories={self.socket_dir} -p {self.port} -c fsync=off"
        self.log = self.root / 'postgres.log'
        # The postmaster inherits pg_ctl's stdio: send it to a file, never a pipe, or the call hangs.
        with open(self.log, 'ab') as log:
            subprocess.run(
                [
                    str(self.bin / 'pg_ctl'),
                    '-D',
                    str(self.data),
                    '-o',
                    options,
                    '-l',
                    str(self.log),
                    '-w',
                    '-s',
                    'start',
                ],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env={**os.environ, 'LC_ALL': 'C'},
                timeout=60,
            )

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            return probe.getsockname()[1]

    @property
    def dsn(self) -> str:
        return f'host={self.socket_dir} port={self.port} user=postgres dbname=postgres'

    def stop(self) -> None:
        subprocess.run(
            [str(self.bin / 'pg_ctl'), '-D', str(self.data), '-m', 'immediate', '-w', '-s', 'stop'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        shutil.rmtree(self.root, ignore_errors=True)


_postgres_state: dict[str, Any] = {}


def iam_target() -> tuple[str, str, str] | None:
    """``OMI_TEST_POSTGRES_IAM=host,database,user``: Cloud SQL over private IP with IAM auth (staging job)."""
    raw = os.getenv('OMI_TEST_POSTGRES_IAM', '').strip()
    if not raw:
        return None
    parts = [part.strip() for part in raw.split(',')]
    if len(parts) != 3 or not all(parts):
        raise BackendUnavailable('OMI_TEST_POSTGRES_IAM must be host,database,user')
    return parts[0], parts[1], parts[2]


def postgres_connect() -> Callable[[], Any]:
    """A connection factory for the migrated test database (IAM when ``OMI_TEST_POSTGRES_IAM`` is set)."""
    target = iam_target()
    if target is not None:
        from database.jobstore.connection import iam_connector

        postgres_dsn()  # migrates once
        return iam_connector(*target)
    dsn = postgres_dsn()
    from database.jobstore.connection import dial

    return lambda: dial(dsn)


def postgres_dsn() -> str:
    """DSN of a migrated test database, started once per process (or the IAM target's label)."""
    if 'dsn' in _postgres_state:
        return _postgres_state['dsn']
    if importlib.util.find_spec('psycopg') is None:
        raise BackendUnavailable('psycopg 3 is not installed')
    target = iam_target()
    if target is not None:
        from database.jobstore.connection import iam_connector
        from database.jobstore.migrate import migrate

        conn = iam_connector(*target)()
        try:
            migrate(conn)  # idempotent: staging-jobstore already applied every migration
        finally:
            conn.close()
        _postgres_state['dsn'] = f'iam:{target[0]}/{target[1]}'  # a label, never a credential
        return _postgres_state['dsn']
    dsn = os.getenv('OMI_TEST_POSTGRES_DSN')
    if dsn:
        local = 'host=/' in dsn or 'localhost' in dsn or '127.0.0.1' in dsn
        if not local and os.getenv('OMI_TEST_POSTGRES_ALLOW_REMOTE') != '1':
            raise BackendUnavailable('remote OMI_TEST_POSTGRES_DSN needs OMI_TEST_POSTGRES_ALLOW_REMOTE=1')
    else:
        bin_dir = _find_postgres_bin()
        if bin_dir is None:
            raise BackendUnavailable('no initdb/postgres on PATH and no pgserver wheel')
        server = LocalPostgres(bin_dir)
        _postgres_state['server'] = server
        atexit.register(stop_local_postgres)
        dsn = server.dsn
    from database.jobstore.connection import dial
    from database.jobstore.migrate import migrate

    conn = dial(dsn)
    try:
        migrate(conn)
    finally:
        conn.close()
    _postgres_state['dsn'] = dsn
    return dsn


def stop_local_postgres() -> None:
    server = _postgres_state.pop('server', None)
    _postgres_state.pop('dsn', None)
    if server is not None:
        server.stop()


# -- backend factories ----------------------------------------------------------------------------------
def _new_ids() -> tuple[str, str]:
    token = uuid.uuid4().hex[:12]
    return f'batch_pipeline_test_{token}', token


def make_sim() -> StoreHarness:
    from testing.pipeline_sim.store import CustomerData, SimStore

    namespace, token = _new_ids()
    customer = CustomerData()
    return StoreHarness('sim', SimStore(customer, namespace=namespace), customer, namespace, token)


def _emulator_client():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        raise BackendUnavailable('loopback Firestore emulator required (FIRESTORE_EMULATOR_HOST); no cloud fallback')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    return firestore.Client(project='demo-omi-isolated-tests', credentials=AnonymousCredentials())


def make_emulator() -> StoreHarness:
    from database.batch_pipeline_store import FirestoreStore

    client = _emulator_client()
    namespace, token = _new_ids()
    store = FirestoreStore(namespace, firestore_client=client)
    harness = StoreHarness('emulator', store, ClientCustomerData(client), namespace, token)

    def cleanup() -> None:
        # Only this harness's own throwaway namespace.
        for table in _BATCH_TABLES:
            for doc in client.collection(f'{namespace}_{table}').stream():
                doc.reference.delete()
        client.close()

    harness.cleanup_steps.append(cleanup)
    return harness


def make_postgres() -> StoreHarness:
    from database.jobstore.connection import Pool
    from database.jobstore.postgres_store import PostgresStore
    from testing.pipeline_sim.store import CustomerData

    connect = postgres_connect()
    namespace, token = _new_ids()
    customer = CustomerData()
    pool = Pool('', connect=connect)
    store = PostgresStore(namespace, pool=pool, customer_client=customer.client, harness_customer_tables=True)
    harness = StoreHarness('postgres', store, customer, namespace, token)

    def cleanup() -> None:
        store.purge_namespace()
        pool.close()

    harness.cleanup_steps.append(cleanup)
    return harness


FACTORIES: dict[str, Callable[[], StoreHarness]] = {
    'sim': make_sim,
    'emulator': make_emulator,
    'postgres': make_postgres,
}


def build_backend(name: str) -> StoreHarness:
    """Build a backend or skip/fail per ``OMI_REQUIRE_STORE_BACKENDS``."""
    try:
        return FACTORIES[name]()
    except BackendUnavailable as exc:
        if name in required_backends():
            pytest.fail(f'required store backend {name!r} unavailable: {exc}')
        pytest.skip(f'{name} backend unavailable: {exc}')
        raise AssertionError('unreachable')


@pytest.fixture(params=BACKENDS)
def store_backend(request) -> Iterator[StoreHarness]:
    harness = build_backend(request.param)
    try:
        yield harness
    finally:
        harness.close()


# -- outbox backends (contract (b)) ---------------------------------------------------------------------------
@dataclass
class OutboxHarness:
    """One Outbox implementation plus the controls the conformance suite needs.

    ``wakes`` records every (row_id, wake_token, available_at) the implementation asked to be woken,
    ``store`` is the backend's batch Store (for the ``tx=`` path) and ``run_tx`` runs ``body(tx)`` in
    one store transaction whose outbox writes commit or roll back with it.
    """

    name: str
    outbox: Any
    store_harness: StoreHarness
    wakes: list[tuple[str, str, float]]
    fail_wakes: list[bool]
    # Adapters from generic test labels to a backend's row shape. Defaults suit the Postgres and sim outboxes.
    key: Callable[[str, str], str] = lambda owner, label: label
    payload: Callable[..., dict] = lambda label, **extra: {'conversation_id': label, **extra}

    def run_tx(self, body: Callable[[Any], Any]) -> Any:
        if self.name == 'sim':
            with self.outbox.transaction():
                return self.store_harness.store.run(body)
        return self.store_harness.store.run(body)


def _privacy_probe(harness: StoreHarness) -> Callable[[str, Any], bool]:
    def blocked(owner_id: str, payload: Any) -> bool:
        conversations = (payload['conversation_id'],) if payload.get('conversation_id') else ()
        return harness.customer.blocked(owner_id, conversations)

    return blocked


def build_outbox_backend(name: str, kind: Any) -> OutboxHarness:
    """Build an outbox backend or skip/fail per ``OMI_REQUIRE_STORE_BACKENDS`` (same rule as stores)."""
    wakes: list[tuple[str, str, float]] = []
    fail_wakes = [False]

    def wake(row_id: str, token: str, available_at: float) -> None:
        if fail_wakes[0]:
            raise RuntimeError('task create failed')
        wakes.append((row_id, token, available_at))

    try:
        harness = FACTORIES[name]()
        if name == 'emulator':
            try:
                from database import outbox_firestore  # lane 9
            except ImportError as exc:
                harness.close()
                raise BackendUnavailable('database/outbox_firestore.py has not landed (lane 9)') from exc
            if not hasattr(outbox_firestore, 'FirestoreOutbox'):
                harness.close()
                raise BackendUnavailable(
                    'outbox_firestore.FirestoreOutbox(kind, client=, privacy_blocked=, create_wake=)'
                )
            outbox_cls: Any = outbox_firestore.FirestoreOutbox
            probe = _privacy_probe(harness)
            from utils.enrichment import outbox as enrichment_outbox  # row keys are (owner, conversation) hashes

            owner = harness.uid('o')
            outbox_rows = harness.customer.client.collection(enrichment_outbox.COLLECTION)

            def drop_outbox_rows() -> None:
                # The enrichment collection is fixed (row compatibility), so remove only this harness's rows.
                for doc in outbox_rows.where('uid', '==', owner).stream():
                    doc.reference.delete()

            harness.cleanup_steps.append(drop_outbox_rows)  # close() runs steps in reverse: before the client closes

            return OutboxHarness(
                name,
                outbox_cls(kind, client=harness.customer.client, privacy_blocked=probe, create_wake=wake),
                harness,
                wakes,
                fail_wakes,
                key=lambda owner, label: enrichment_outbox.key(owner, label),
                payload=lambda label, **extra: {'conversation_id': label, 'language': 'en', **extra},
            )
    except BackendUnavailable as exc:
        if name in required_backends():
            pytest.fail(f'required outbox backend {name!r} unavailable: {exc}')
        pytest.skip(f'{name} outbox backend unavailable: {exc}')
        raise AssertionError('unreachable')
    probe = _privacy_probe(harness)
    if name == 'sim':
        from testing.outbox_sim import SimOutbox

        outbox: Any = SimOutbox(kind, privacy_blocked=probe, create_wake=wake)
    else:
        from database.jobstore.outbox_pg import PostgresOutbox

        outbox = PostgresOutbox(kind, harness.store, privacy_blocked=probe, create_wake=wake)
    return OutboxHarness(name, outbox, harness, wakes, fail_wakes)


@pytest.fixture(params=BACKENDS)
def outbox_backend(request) -> Iterator[OutboxHarness]:
    from database.outbox import OutboxKind

    harness = build_outbox_backend(request.param, OutboxKind.ENRICHMENT)
    try:
        yield harness
    finally:
        harness.store_harness.close()
