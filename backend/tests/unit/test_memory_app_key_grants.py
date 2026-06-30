from database.memory_app_key_grants import (
    APP_KEY_MEMORY_GRANT_DOC_ID,
    APP_KEY_MEMORY_GRANT_SUBPATH,
    APP_KEY_MEMORY_GRANTS_COLLECTION,
    build_app_key_scope_grant_contract_state,
    read_app_key_memory_grants_state,
)
from utils.memory.product_authorization import (
    MemoryGrantOperation,
    ProductAuthorizationContext,
    authorize_app_key_scope_memory_grant,
)


class FakeSnapshot:
    def __init__(self, exists, data=None):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class FakeDocument:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get(self):
        return self.snapshot


class FakeCollection:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def document(self, document_id):
        self.db.document_paths.append(f'{self.path}/{document_id}')
        return FakeDocument(self.db.snapshots.get(f'{self.path}/{document_id}', FakeSnapshot(False)))


class FakeDb:
    def __init__(self, snapshots=None):
        self.snapshots = snapshots or {}
        self.collection_paths = []
        self.document_paths = []

    def collection(self, collection_name):
        self.collection_paths.append(collection_name)
        return FakeCollection(self, collection_name)


def _context(scopes=('memories.read',)):
    return ProductAuthorizationContext(
        uid='user-123',
        consumer='developer_api',
        surface='unit-test',
        app_id='app-abc',
        key_id='key-def',
        scopes=scopes,
    )


def test_read_app_key_memory_grants_state_reads_exact_server_owned_path():
    doc_path = f'users/user-123/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    state = build_app_key_scope_grant_contract_state(
        consumer='developer_api',
        app_id='app-abc',
        key_id='key-def',
        scopes=['memories.read'],
        default_read=True,
    )
    db = FakeDb({doc_path: FakeSnapshot(True, state)})

    decision = read_app_key_memory_grants_state(uid='user-123', db_client=db)

    assert decision.present is True
    assert decision.malformed is False
    assert decision.state == state
    assert decision.source_path == doc_path
    assert db.collection_paths == ['users/user-123/memory_control']
    assert db.document_paths == [doc_path]
    assert APP_KEY_MEMORY_GRANTS_COLLECTION == 'memory_control'
    assert APP_KEY_MEMORY_GRANT_DOC_ID == 'app_key_memory_grants'


def test_missing_app_key_memory_grants_state_returns_absent_state():
    db = FakeDb()

    decision = read_app_key_memory_grants_state(uid='user-123', db_client=db)

    assert decision.present is False
    assert decision.malformed is False
    assert decision.state == {}
    assert decision.reason == 'missing_app_key_memory_grants_state'


def test_malformed_app_key_memory_grants_state_is_detected_and_fails_closed():
    doc_path = f'users/user-123/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    db = FakeDb({doc_path: FakeSnapshot(True, {'grants': []})})

    state_decision = read_app_key_memory_grants_state(uid='user-123', db_client=db)
    grant_decision = authorize_app_key_scope_memory_grant(
        _context(),
        persisted_grant_state=state_decision.state,
        operation=MemoryGrantOperation.DEFAULT_READ,
    )

    assert state_decision.present is True
    assert state_decision.malformed is True
    assert state_decision.reason == 'malformed_app_key_memory_grants_state'
    assert grant_decision.allowed is False
    assert grant_decision.reason == 'malformed_app_key_scope_grant'


def test_valid_memory_app_key_memory_grant_state_feeds_default_read_authorization():
    doc_path = f'users/user-123/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    state = build_app_key_scope_grant_contract_state(
        consumer='developer_api',
        app_id='app-abc',
        key_id='key-def',
        scopes=['memories.read'],
        default_read=True,
    )
    db = FakeDb({doc_path: FakeSnapshot(True, state)})

    state_decision = read_app_key_memory_grants_state(uid='user-123', db_client=db)
    grant_decision = authorize_app_key_scope_memory_grant(
        _context(),
        persisted_grant_state=state_decision.state,
        operation=MemoryGrantOperation.DEFAULT_READ,
    )

    assert grant_decision.allowed is True
    assert grant_decision.reason == 'ok'
    assert grant_decision.grant_path == 'grants.developer_api.apps.app-abc.keys.key-def'
    assert grant_decision.policy.app_has_default_memory_grant is True
    assert grant_decision.policy.archive_capability is False


def test_archive_grant_does_not_make_default_read_archive_visible_without_archive_operation():
    doc_path = f'users/user-123/{APP_KEY_MEMORY_GRANT_SUBPATH}'
    state = build_app_key_scope_grant_contract_state(
        consumer='developer_api',
        app_id='app-abc',
        key_id='key-def',
        scopes=['memories.read', 'memories.archive.read'],
        default_read=True,
        archive_read=True,
    )
    db = FakeDb({doc_path: FakeSnapshot(True, state)})

    state_decision = read_app_key_memory_grants_state(uid='user-123', db_client=db)
    default_decision = authorize_app_key_scope_memory_grant(
        _context(scopes=('memories.read', 'memories.archive.read')),
        persisted_grant_state=state_decision.state,
        operation=MemoryGrantOperation.DEFAULT_READ,
    )
    archive_decision = authorize_app_key_scope_memory_grant(
        _context(scopes=('memories.read', 'memories.archive.read')),
        persisted_grant_state=state_decision.state,
        operation=MemoryGrantOperation.ARCHIVE_READ,
    )

    assert default_decision.allowed is True
    assert default_decision.policy.archive_capability is False
    assert archive_decision.allowed is True
    assert archive_decision.policy.archive_capability is True
