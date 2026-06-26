import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'utils',
)


def _should_stub(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + '.') for prefix in _STUB_PREFIXES)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _StubFinder())

from services.users import account_deletion  # noqa: E402


def test_start_account_deletion_preserves_order_and_enqueues_background_wipe(monkeypatch):
    calls = []
    sub = types.SimpleNamespace(stripe_subscription_id='sub_123')

    monkeypatch.setattr(
        account_deletion.users_db,
        'set_user_deletion_feedback',
        lambda uid, reason, details: calls.append(('feedback', uid, reason, details)),
    )
    monkeypatch.setattr(
        account_deletion.users_db, 'get_user_subscription', lambda uid: calls.append(('sub', uid)) or sub
    )
    monkeypatch.setattr(
        account_deletion.stripe_utils,
        'cancel_subscription',
        lambda sub_id: calls.append(('stripe', sub_id)) or object(),
    )
    monkeypatch.setattr(account_deletion.auth, 'delete_account', lambda uid: calls.append(('auth', uid)))

    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: calls.append(('enqueue', executor, target, uid)),
    )

    result = account_deletion.start_account_deletion('uid1', reason='unused', reason_details='details')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    assert calls == [
        ('feedback', 'uid1', 'unused', 'details'),
        ('sub', 'uid1'),
        ('stripe', 'sub_123'),
        ('auth', 'uid1'),
        ('enqueue', account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'),
    ]


def test_start_account_deletion_tolerates_best_effort_failures_and_missing_firebase_user(monkeypatch):
    monkeypatch.setattr(
        account_deletion.users_db, 'set_user_deletion_feedback', MagicMock(side_effect=Exception('db down'))
    )
    monkeypatch.setattr(
        account_deletion.users_db, 'get_user_subscription', MagicMock(side_effect=Exception('read down'))
    )
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('USER_NOT_FOUND')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.start_account_deletion('uid1', reason='reason')

    assert result['status'] == 'ok'
    account_deletion.stripe_utils.cancel_subscription.assert_not_called()
    submit.assert_called_once_with(
        account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'
    )


def test_start_account_deletion_raises_unexpected_firebase_error(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('permission denied')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert str(exc) == 'permission denied'
    else:
        raise AssertionError('expected firebase error to propagate')

    submit.assert_not_called()


def test_background_wipe_user_data_preserves_order(monkeypatch):
    calls = []
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', lambda uid: calls.append(('twilio', uid)))
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', lambda uid: calls.append(('purge', uid)))
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', lambda uid: calls.append(('firestore', uid)))

    account_deletion.background_wipe_user_data('uid1')

    assert calls == [('twilio', 'uid1'), ('purge', 'uid1'), ('firestore', 'uid1')]


def test_background_wipe_user_data_swallows_failures(monkeypatch):
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock(side_effect=Exception('twilio down')))
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())

    account_deletion.background_wipe_user_data('uid1')

    account_deletion.purge_derived_user_data.assert_not_called()
    account_deletion.users_db.delete_user_data.assert_not_called()


def test_purge_derived_user_data_isolates_backends_and_reloads_conversation_ids(monkeypatch):
    calls = []
    conversation_calls = iter([['c1'], ['c2']])
    monkeypatch.setattr(
        account_deletion,
        'get_conversation_ids',
        lambda uid: calls.append(('get_conversations', uid)) or next(conversation_calls),
    )
    monkeypatch.setattr(account_deletion, 'get_memory_ids', lambda uid: calls.append(('get_memories', uid)) or ['m1'])
    monkeypatch.setattr(
        account_deletion, 'get_action_item_ids', lambda uid: calls.append(('get_actions', uid)) or ['a1']
    )
    monkeypatch.setattr(
        account_deletion, 'get_screen_activity_ids', lambda uid: calls.append(('get_screen', uid)) or ['s1']
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_conversation_vectors_batch',
        lambda uid, ids: calls.append(('delete_conversation_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_transcript_chunk_vectors_batch',
        lambda uid, ids: calls.append(('delete_transcript_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_memory_vectors_batch',
        lambda uid, ids: calls.append(('delete_memory_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_action_item_vectors_batch',
        lambda uid, ids: calls.append(('delete_action_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_screen_activity_vectors',
        lambda uid, ids: calls.append(('delete_screen_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion, 'delete_all_conversation_recordings', lambda uid: calls.append(('recordings', uid))
    )

    account_deletion.purge_derived_user_data('uid1')

    assert calls == [
        ('get_conversations', 'uid1'),
        ('delete_conversation_vectors', 'uid1', ['c1']),
        ('get_conversations', 'uid1'),
        ('delete_transcript_vectors', 'uid1', ['c2']),
        ('get_memories', 'uid1'),
        ('delete_memory_vectors', 'uid1', ['m1']),
        ('get_actions', 'uid1'),
        ('delete_action_vectors', 'uid1', ['a1']),
        ('get_screen', 'uid1'),
        ('delete_screen_vectors', 'uid1', ['s1']),
        ('recordings', 'uid1'),
    ]


def test_purge_derived_user_data_continues_after_each_failure(monkeypatch):
    monkeypatch.setattr(account_deletion, 'get_conversation_ids', MagicMock(side_effect=Exception('read down')))
    monkeypatch.setattr(account_deletion, 'delete_conversation_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_transcript_chunk_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'get_memory_ids', MagicMock(return_value=['m1']))
    monkeypatch.setattr(
        account_deletion, 'delete_memory_vectors_batch', MagicMock(side_effect=Exception('pinecone down'))
    )
    monkeypatch.setattr(account_deletion, 'get_action_item_ids', MagicMock(return_value=['a1']))
    monkeypatch.setattr(account_deletion, 'delete_action_item_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'get_screen_activity_ids', MagicMock(return_value=['s1']))
    monkeypatch.setattr(account_deletion, 'delete_screen_activity_vectors', MagicMock())
    monkeypatch.setattr(
        account_deletion, 'delete_all_conversation_recordings', MagicMock(side_effect=Exception('gcs down'))
    )

    account_deletion.purge_derived_user_data('uid1')

    assert account_deletion.get_conversation_ids.call_count == 2
    account_deletion.delete_conversation_vectors_batch.assert_not_called()
    account_deletion.delete_transcript_chunk_vectors_batch.assert_not_called()
    account_deletion.delete_memory_vectors_batch.assert_called_once_with('uid1', ['m1'])
    account_deletion.delete_action_item_vectors_batch.assert_called_once_with('uid1', ['a1'])
    account_deletion.delete_screen_activity_vectors.assert_called_once_with('uid1', ['s1'])
    account_deletion.delete_all_conversation_recordings.assert_called_once_with('uid1')
