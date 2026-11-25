"""PL-767: upload-ledger erasure on Firestore and its synchronous PostgreSQL copy."""

import os
import shlex
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from tests.integration.test_conversation_batch_purge_emulator import plane  # noqa: F401

pytestmark = pytest.mark.integration


def _is_loopback_postgres_dsn(dsn: str) -> bool:
    """Accept only explicit loopback hosts or Unix sockets for this synthetic-data proof."""
    try:
        if dsn.lower().startswith(("postgres://", "postgresql://")):
            parsed = urlsplit(dsn)
            query = {key.lower(): values for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
            hosts = query.get("host", [parsed.hostname or ""])
            hostaddrs = query.get("hostaddr", [])
            options = {key.lower() for key in query}
        else:
            values = {}
            for part in shlex.split(dsn):
                key, separator, value = part.partition("=")
                if not separator:
                    return False
                values.setdefault(key.lower(), []).append(value)
            hosts = values.get("host", [""])
            hostaddrs = values.get("hostaddr", [])
            options = set(values)
    except (ValueError, UnicodeError):
        return False

    # Service files can supply a different target, so this fixture deliberately refuses them.
    if "service" in options or "servicefile" in options:
        return False
    allowed_hosts = {"", "localhost", "127.0.0.1", "::1"}
    if not all(host.lower() in allowed_hosts or host.startswith("/") for entry in hosts for host in entry.split(",")):
        return False
    return all(
        not address or address.strip("[]").lower() in {"127.0.0.1", "::1"}
        for entry in hostaddrs
        for address in entry.split(",")
    )


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost port=5432",
        "host=127.0.0.1 port=5432",
        "host=::1 port=5432",
        "host=/var/run/postgresql dbname=postgres",
        "postgresql://postgres@localhost/postgres",
        "postgresql://postgres@[::1]/postgres",
    ],
)
def test_loopback_postgres_dsn_is_accepted(dsn):
    assert _is_loopback_postgres_dsn(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "host=db-notlocalhost.example dbname=postgres",
        "host=localhost host=db-notlocalhost.example dbname=postgres",
        "host=localhost,db.example dbname=postgres",
        "host=localhost hostaddr=203.0.113.7 dbname=postgres",
        "service=staging",
        "postgresql://postgres@db-notlocalhost.example/postgres",
        "postgresql://localhost/postgres?Host=db-notlocalhost.example",
    ],
)
def test_remote_postgres_dsn_is_rejected(dsn):
    assert not _is_loopback_postgres_dsn(dsn)


@pytest.fixture(params=['firestore', 'postgres-copy'])
def ledger_purge_stores(request, plane, monkeypatch):
    from database.batch_pipeline_store import FirestoreStore
    from database.jobstore import dual_store
    from testing.store_fixtures import BackendUnavailable, make_postgres, required_backends

    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    # No best-effort refresh can erase the replacement copy before the purge barrier.
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'firestore')
    for name in ('JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER'):
        monkeypatch.delenv(name, raising=False)
    if request.param == 'firestore':
        primary = FirestoreStore(f'batch_pipeline_test_{uuid4().hex[:12]}', firestore_client=plane.client)
        yield (primary,)
        return
    # This synthetic-data proof must never use a staging IAM target or caller-supplied remote DSN.
    for name in ('OMI_TEST_POSTGRES_IAM', 'OMI_TEST_POSTGRES_ALLOW_REMOTE'):
        monkeypatch.delenv(name, raising=False)
    dsn = os.getenv('OMI_TEST_POSTGRES_DSN')
    if dsn and not _is_loopback_postgres_dsn(dsn):
        raise BackendUnavailable('PL-767 requires a loopback or Unix-socket OMI_TEST_POSTGRES_DSN')
    for name in ('PGHOST', 'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE'):
        monkeypatch.delenv(name, raising=False)
    try:
        postgres = make_postgres()
    except BackendUnavailable as exc:
        if 'postgres' in required_backends():
            pytest.fail(f'required local postgres backend unavailable: {exc}')
        pytest.skip(str(exc))
    try:
        primary = FirestoreStore(postgres.namespace, firestore_client=plane.client)
        monkeypatch.setitem(dual_store._SHADOWED, primary.namespace, dual_store.DualStore(primary, postgres.store))
        yield primary, postgres.store
    finally:
        postgres.close()


def test_pl767_purge_follows_provisional_upload_identity_in_both_stores(plane, ledger_purge_stores):
    from database.batch_pipeline_privacy import privacy_owner_key
    from database.batch_pipeline_purge import purge_batch_owner
    from utils.sync.stage import collection_name

    stores = ledger_purge_stores
    namespace = stores[0].namespace
    owner = plane.client.collection('users').document(plane.uid)
    foreign = plane.client.collection('users').document('synthetic-foreign')
    tombstones = owner.collection('deleted_conversations')
    ledger = collection_name('sync_content_ledger')
    foreign.set({'data_protection_level': 'standard'})
    tombstones.document('deleted-window').set({'id': 'deleted-window'})
    owner.collection('conversations').document('live-window').set({'status': 'completed'})

    def upload(account, segment, *windows):
        account.collection(ledger).document(segment).set(
            {
                'job_id': f'upload-{segment}',
                'partial_result': {'updated_memories': list(windows)},
                'batch_pipeline': {'namespace': namespace, 'segment_ids': [segment]},
            }
        )

    upload(owner, 'exclusive', 'deleted-window')
    upload(owner, 'shared', 'deleted-window', 'live-window')
    upload(owner, 'unrelated', 'live-window')
    upload(foreign, 'foreign-ledger', 'deleted-window')
    # Even an erroneous old row in this owner's ledger cannot authorize a foreign batch row.
    upload(owner, 'foreign-row', 'deleted-window')
    ledger_docs = {
        ('owner', segment): owner.collection(ledger).document(segment)
        for segment in ('exclusive', 'shared', 'unrelated', 'foreign-row')
    }
    ledger_docs[('foreign', 'foreign-ledger')] = foreign.collection(ledger).document('foreign-ledger')
    ledger_before = {key: ref.get().to_dict() for key, ref in ledger_docs.items()}
    assert all(value is not None for value in ledger_before.values())

    def assert_ledgers_untouched():
        assert {key: ref.get().to_dict() for key, ref in ledger_docs.items()} == ledger_before

    def batch_rows(segment, uid=plane.uid):
        owner_fields = {'owner_id': uid, 'owner_key': privacy_owner_key(uid)}
        binding = {**owner_fields, 'segment_id': segment, 'conversation_id': f'capture-{segment}'}
        return {
            'jobs': {**binding, 'priority': 1, 'state': 'committed', 'audio_uri': f'gs://synthetic/{segment}/audio'},
            'results': {
                **binding,
                'projection_state': 'completed',
                'previous_segment_id': 'prior-slot',
                'result': {'result_uri': f'gs://synthetic/{segment}/transcript'},
            },
            'artifacts': {**owner_fields, 'segment_id': segment, 'uri': f'gs://synthetic/{segment}/artifact'},
            'intakes': {**owner_fields, 'segment_ids': [segment]},
        }

    seeded = {
        'exclusive': batch_rows('exclusive'),
        'shared': batch_rows('shared'),
        'unrelated': batch_rows('unrelated'),
        'foreign-ledger': batch_rows('foreign-ledger'),
        'foreign-row': batch_rows('foreign-row', foreign.id),
    }

    # Seed historical rows directly: the provisional capture IDs are no longer live Conversation documents.
    batch = plane.client.batch()
    for segment, rows in seeded.items():
        for table, doc in rows.items():
            batch.set(plane.client.collection(f'{namespace}_{table}').document(segment), doc)
    batch.commit()
    for copy in stores[1:]:
        with copy.pool.connection() as conn, conn.transaction():
            for segment, rows in seeded.items():
                for table, doc in rows.items():
                    copy.write_doc(conn, table, segment, doc)

    def read(tx):
        return {segment: {table: tx.get(table, segment) for table in rows} for segment, rows in seeded.items()}

    before = [store.run(read) for store in stores]
    assert before == [seeded] * len(stores)
    removed = set()

    def purge(cid):
        purge_batch_owner(
            plane.uid,
            firestore_client=plane.client,
            conversation_id=cid,
            namespaces=(namespace,),
            delete_uri=lambda uid, uri: removed.add((uid, uri)),
        )

    def erased(segment):
        return {
            'jobs': {},
            'results': {
                'segment_id': segment,
                'owner_key': plane.key,
                'projection_state': 'erased',
                'previous_segment_id': 'prior-slot',
            },
            'artifacts': {},
            'intakes': {},
        }

    purge('deleted-window')
    expected = {**seeded, 'exclusive': erased('exclusive')}
    assert [store.run(read) for store in stores] == [expected] * len(stores)
    assert_ledgers_untouched()
    assert removed == {(plane.uid, f'gs://synthetic/exclusive/{kind}') for kind in ('audio', 'transcript', 'artifact')}

    # A formerly shared upload becomes eligible when its final sibling is deleted.
    tombstones.document('live-window').set({'id': 'live-window'})
    removed.clear()
    purge('live-window')
    expected.update(shared=erased('shared'), unrelated=erased('unrelated'))
    assert [store.run(read) for store in stores] == [expected] * len(stores)
    assert_ledgers_untouched()
    assert removed == {
        (plane.uid, f'gs://synthetic/{segment}/{kind}')
        for segment in ('shared', 'unrelated')
        for kind in ('audio', 'transcript', 'artifact')
    }
