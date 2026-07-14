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
    def __init__(self):
        self._created: set[str] = set()

    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        self._created.add(spec.name)
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


_finder = _StubFinder()
sys.meta_path.insert(0, _finder)
try:
    from services.users import account_deletion  # noqa: E402
finally:
    # Remove the meta-path finder and clear *only* the modules that the
    # stub finder actually created. Broadly deleting every module matching
    # _STUB_PREFIXES (database, utils, …) would also evict real project
    # modules imported by other tests collected in the same pytest process.
    sys.meta_path.remove(_finder)
    for _name in list(_finder._created):
        sys.modules.pop(_name, None)
    # The imported service module itself was loaded against the MagicMock
    # stubs (its globals hold MagicMock objects for users_db, stripe_utils,
    # etc.). Pop it — along with its parent packages — so a later test that
    # imports the real service reloads it with production dependencies
    # instead of reusing this mock-backed copy.
    for _svc_name in ('services.users.account_deletion', 'services.users', 'services'):
        sys.modules.pop(_svc_name, None)


def test_start_account_deletion_preserves_order_and_enqueues_background_wipe(monkeypatch):
    calls = []
    sub = types.SimpleNamespace(stripe_subscription_id='sub_123')

    monkeypatch.setattr(
        account_deletion.users_db,
        'set_user_deletion_feedback',
        lambda uid, reason, details: calls.append(('feedback', uid, reason, details)),
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        lambda uid: calls.append(('wipe_intent', uid)) or 'job-1',
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_started',
        lambda uid: calls.append(('wipe_started', uid)),
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
        ('wipe_intent', 'uid1'),
        ('sub', 'uid1'),
        ('stripe', 'sub_123'),
        ('auth', 'uid1'),
        ('wipe_started', 'uid1'),
        ('enqueue', account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'),
    ]


def test_start_account_deletion_enqueues_cloud_task_when_enabled(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.start_account_deletion('uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    enqueue.assert_called_once_with('job-1')
    submit.assert_not_called()


def test_start_account_deletion_raises_when_cloud_task_enqueue_fails(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(
        account_deletion, 'enqueue_account_deletion_wipe', MagicMock(side_effect=Exception('tasks down'))
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert str(exc) == 'tasks down'
    else:
        raise AssertionError('expected enqueue failure to raise')

    account_deletion.users_db.mark_user_deletion_wipe_started.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    submit.assert_not_called()


def test_start_account_deletion_tolerates_feedback_failure_and_missing_firebase_user(monkeypatch):
    """Feedback failures are tolerated, but marker and billing checks must succeed."""
    monkeypatch.setattr(
        account_deletion.users_db, 'set_user_deletion_feedback', MagicMock(side_effect=Exception('db down'))
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        MagicMock(return_value='job-1'),
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_started',
        MagicMock(),
    )
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('USER_NOT_FOUND')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    result = account_deletion.start_account_deletion('uid1', reason='reason')

    assert result['status'] == 'ok'
    account_deletion.stripe_utils.cancel_subscription.assert_not_called()
    submit.assert_called_once_with(
        account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'
    )


def test_start_account_deletion_blocks_when_subscription_lookup_fails(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    monkeypatch.setattr(
        account_deletion.users_db, 'get_user_subscription', MagicMock(side_effect=Exception('read down'))
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_billing_failed', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert str(exc) == 'read down'
    else:
        raise AssertionError('expected subscription lookup failure to raise')

    account_deletion.users_db.mark_user_deletion_billing_failed.assert_called_once_with('uid1', None, 'read down')
    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_blocks_when_stripe_cancel_returns_none(monkeypatch):
    sub = types.SimpleNamespace(stripe_subscription_id='sub_123')
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=sub))
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_billing_failed', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert 'stripe cancel returned no subscription' in str(exc)
    else:
        raise AssertionError('expected stripe cancellation failure to raise')

    account_deletion.users_db.mark_user_deletion_billing_failed.assert_called_once_with(
        'uid1', 'sub_123', 'stripe cancel returned no subscription'
    )
    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_raises_when_marker_persist_fails(monkeypatch):
    """If the durable intent cannot be written, the deletion must NOT proceed."""
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(side_effect=Exception('firestore down'))
    )
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert 'intent' in str(exc).lower() or 'deletion-wipe' in str(exc).lower()
    else:
        raise AssertionError('expected intent failure to raise')

    # Firebase user must NOT be deleted if the intent failed.
    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_raises_when_pending_marker_persist_fails_after_auth(monkeypatch):
    """Do not enqueue or report success unless the actionable pending marker exists."""
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(side_effect=Exception('db down'))
    )
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert 'marker transition to pending failed' in str(exc)
    else:
        raise AssertionError('expected pending marker failure to raise')

    account_deletion.auth.delete_account.assert_called_once_with('uid1')
    submit.assert_not_called()


def test_start_account_deletion_raises_unexpected_firebase_error(monkeypatch):
    """Firebase errors propagate. The intent IS written first, then cancelled on failure; Phase 2 is never reached."""
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value='job-1'))
    mark_started = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', mark_started)
    cancel_wipe = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'cancel_user_deletion_wipe', cancel_wipe)
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('permission denied')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert str(exc) == 'permission denied'
    else:
        raise AssertionError('expected firebase error to propagate')

    submit.assert_not_called()
    # Phase 1 intent IS written BEFORE Firebase deletion.
    account_deletion.users_db.mark_user_deletion_wipe_intent.assert_called_once_with('uid1')
    # On Firebase failure, the intent is cancelled so the record doesn't linger.
    cancel_wipe.assert_called_once_with('uid1')
    # Phase 2 (transition to 'pending') is never reached on auth failure.
    mark_started.assert_not_called()


def test_start_account_deletion_writes_intent_before_pending(monkeypatch):
    """P1 safety: the non-actionable 'deleting_auth' intent is written before
    auth deletion, and the actionable 'pending' marker is written only after
    auth deletion is confirmed.

    This verifies the two-phase ordering that prevents a crash between the
    intent write and auth deletion from leaving an actionable 'pending' marker
    that the reconciler could prematurely act on.
    """
    call_log = []
    intent_mock = MagicMock(side_effect=lambda uid: call_log.append('intent') or 'job-1')
    started_mock = MagicMock(side_effect=lambda uid: call_log.append('started'))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', intent_mock)
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', started_mock)
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(
        account_deletion.auth, 'delete_account', MagicMock(side_effect=lambda uid: call_log.append('auth'))
    )
    monkeypatch.setattr(account_deletion, 'submit_with_context', MagicMock())
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    account_deletion.start_account_deletion('uid1')

    # Intent is written before auth, started is written after auth.
    assert call_log == ['intent', 'auth', 'started']
    intent_mock.assert_called_once_with('uid1')
    started_mock.assert_called_once_with('uid1')


def test_background_wipe_user_data_preserves_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_running', lambda uid: calls.append(('running', uid))
    )
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', lambda uid: calls.append(('twilio', uid)))
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', lambda uid: calls.append(('purge', uid)))
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', lambda uid: calls.append(('firestore', uid)))
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_completed', lambda uid: calls.append(('wipe_done', uid))
    )

    account_deletion.background_wipe_user_data('uid1')

    assert calls == [
        ('running', 'uid1'),
        ('twilio', 'uid1'),
        ('purge', 'uid1'),
        ('firestore', 'uid1'),
        ('wipe_done', 'uid1'),
    ]


def test_background_wipe_user_data_swallows_failures(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock(side_effect=Exception('twilio down')))
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    account_deletion.background_wipe_user_data('uid1')

    account_deletion.purge_derived_user_data.assert_not_called()
    account_deletion.users_db.delete_user_data.assert_not_called()
    # On failure, mark as failed (not completed) so a reconciliation worker can retry.
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()


def test_background_wipe_continues_when_running_marker_persist_fails(monkeypatch):
    """A failure to transition to ``running`` is non-fatal — the wipe still runs."""
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock(side_effect=Exception('firestore down'))
    )
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    # Should not raise — the wipe proceeds even if the running marker can't be written.
    account_deletion.background_wipe_user_data('uid1')

    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_called_once_with('uid1')


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
        lambda uid, ids, **kwargs: calls.append(('delete_transcript_vectors', uid, ids, kwargs)),
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
    monkeypatch.setattr(account_deletion, 'purge_canonical_derived_user_data', MagicMock())

    result = account_deletion.purge_derived_user_data('uid1')

    assert calls == [
        ('get_conversations', 'uid1'),
        ('delete_conversation_vectors', 'uid1', ['c1']),
        ('get_conversations', 'uid1'),
        ('delete_transcript_vectors', 'uid1', ['c2'], {'raise_on_failure': True}),
        ('get_memories', 'uid1'),
        ('delete_memory_vectors', 'uid1', ['m1']),
        ('get_actions', 'uid1'),
        ('delete_action_vectors', 'uid1', ['a1']),
        ('get_screen', 'uid1'),
        ('delete_screen_vectors', 'uid1', ['s1']),
        ('recordings', 'uid1'),
    ]
    assert result == {'required_failures': [], 'best_effort_failures': []}


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
    monkeypatch.setattr(
        account_deletion, 'purge_canonical_derived_user_data', MagicMock(side_effect=Exception('canonical down'))
    )

    result = account_deletion.purge_derived_user_data('uid1')

    assert account_deletion.get_conversation_ids.call_count == 2
    account_deletion.delete_conversation_vectors_batch.assert_not_called()
    account_deletion.delete_transcript_chunk_vectors_batch.assert_not_called()
    account_deletion.delete_memory_vectors_batch.assert_called_once_with('uid1', ['m1'])
    account_deletion.delete_action_item_vectors_batch.assert_called_once_with('uid1', ['a1'])
    account_deletion.delete_screen_activity_vectors.assert_called_once_with('uid1', ['s1'])
    account_deletion.delete_all_conversation_recordings.assert_called_once_with('uid1')
    account_deletion.purge_canonical_derived_user_data.assert_called_once_with('uid1')
    assert [failure['operation'] for failure in result['required_failures']] == [
        'conversation_vectors',
        'transcript_chunk_vectors',
        'memory_vectors',
        'conversation_recordings',
        'canonical_derived_data',
    ]
    assert result['best_effort_failures'] == []


def test_purge_derived_user_data_fails_required_vectors_when_index_missing(monkeypatch):
    monkeypatch.setattr(account_deletion.vector_db, 'index', None)
    monkeypatch.setattr(account_deletion, 'get_conversation_ids', MagicMock(return_value=['c1']))
    monkeypatch.setattr(account_deletion, 'get_memory_ids', MagicMock(return_value=['m1']))
    monkeypatch.setattr(account_deletion, 'get_action_item_ids', MagicMock(return_value=['a1']))
    monkeypatch.setattr(account_deletion, 'get_screen_activity_ids', MagicMock(return_value=['s1']))
    monkeypatch.setattr(account_deletion, 'delete_conversation_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_transcript_chunk_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_memory_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_action_item_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_screen_activity_vectors', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_all_conversation_recordings', MagicMock())
    monkeypatch.setattr(account_deletion, 'purge_canonical_derived_user_data', MagicMock())

    result = account_deletion.purge_derived_user_data('uid1')

    assert [failure['operation'] for failure in result['required_failures']] == [
        'conversation_vectors',
        'transcript_chunk_vectors',
        'memory_vectors',
        'action_item_vectors',
        'screen_activity_vectors',
    ]
    account_deletion.delete_conversation_vectors_batch.assert_not_called()
    account_deletion.delete_transcript_chunk_vectors_batch.assert_not_called()
    account_deletion.delete_memory_vectors_batch.assert_not_called()
    account_deletion.delete_action_item_vectors_batch.assert_not_called()
    account_deletion.delete_screen_activity_vectors.assert_not_called()


def test_background_wipe_user_data_does_not_complete_when_required_derived_purge_fails(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(return_value={'required_failures': [{'operation': 'memory_vectors', 'error': 'down'}]}),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    account_deletion.background_wipe_user_data('uid1')

    account_deletion.users_db.delete_user_data.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()


def test_reconcile_pending_deletion_wipes_re_enqueues(monkeypatch):
    pending = [
        {'uid': 'uid1', 'wipe_status': 'pending', 'wipe_job_id': 'job-1'},
        {'uid': 'uid2', 'wipe_status': 'failed', 'wipe_job_id': 'job-2'},
    ]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append((executor, target, uid)),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 2, 'skipped': 0}
    assert len(enqueued) == 2
    assert enqueued[0] == (account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1')
    assert enqueued[1] == (account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid2')


def test_reconcile_pending_deletion_wipes_enqueues_cloud_tasks(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'failed', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    enqueue.assert_called_once_with('job-1')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_backfills_missing_job_id(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    ensure = MagicMock(return_value='job-recovered')
    monkeypatch.setattr(account_deletion.users_db, 'ensure_deletion_wipe_job_id', ensure)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    ensure.assert_called_once_with('uid1')
    enqueue.assert_called_once_with('job-recovered')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_marks_failed_when_job_id_recovery_fails(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(
        account_deletion.users_db,
        'ensure_deletion_wipe_job_id',
        MagicMock(side_effect=Exception('job id backfill down')),
    )
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    enqueue.assert_not_called()
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_cloud_enqueue_failure(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'failed', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(
        account_deletion, 'enqueue_account_deletion_wipe', MagicMock(side_effect=Exception('tasks down'))
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_already_claimed(monkeypatch):
    """Wipes already claimed by another worker are skipped (no double-enqueue)."""
    pending = [
        {'uid': 'uid1', 'wipe_status': 'pending', 'wipe_job_id': 'job-1'},
        {'uid': 'uid2', 'wipe_status': 'failed', 'wipe_job_id': 'job-2'},
    ]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # uid1 claimable, uid2 already claimed by another worker.
    monkeypatch.setattr(
        account_deletion.users_db,
        'claim_deletion_wipe',
        lambda uid: uid if uid == 'uid1' else None,
    )
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 1}
    assert enqueued == ['uid1']


def test_reconcile_pending_deletion_wipes_skips_claim_exception(monkeypatch):
    """Claim exceptions are logged and skipped, not propagated."""
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(
        account_deletion.users_db,
        'claim_deletion_wipe',
        MagicMock(side_effect=Exception('txn conflict')),
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_missing_uid(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_job_id': 'job-1'}, {'wipe_status': 'pending'}]  # second record has no uid
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 1}
    assert enqueued == ['uid1']


def test_reconcile_pending_deletion_wipes_handles_query_error(monkeypatch):
    monkeypatch.setattr(
        account_deletion.users_db,
        'get_pending_deletion_wipes',
        MagicMock(side_effect=Exception('firestore down')),
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 0, 'error': 1}
    submit.assert_not_called()


def test_reconcile_recovers_deleting_auth_when_user_gone(monkeypatch):
    """Stale 'deleting_auth' record with Firebase user deleted → recovered."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(side_effect=Exception('USER_NOT_FOUND')))
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    assert enqueued == ['uid1']


def test_reconcile_skips_deleting_auth_when_user_exists(monkeypatch):
    """Stale 'deleting_auth' record but Firebase user still exists → skipped."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # get_user succeeds → user exists
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(return_value=object()))
    claim = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', claim)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    claim.assert_not_called()
    submit.assert_not_called()


def test_reconcile_skips_deleting_auth_on_indeterminate_error(monkeypatch):
    """Stale 'deleting_auth' with indeterminate Firebase error → skipped (fail safe)."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # Indeterminate error — not USER_NOT_FOUND
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(side_effect=Exception('internal error')))
    claim = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', claim)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    claim.assert_not_called()
    submit.assert_not_called()


def test_is_auth_user_gone_returns_true_for_user_not_found(monpatch=None):
    """_is_auth_user_gone returns True when Firebase reports USER_NOT_FOUND."""
    # Direct unit test of the helper.
    original_get_user = account_deletion.auth.get_user
    account_deletion.auth.get_user = MagicMock(side_effect=Exception('USER_NOT_FOUND'))
    try:
        assert account_deletion._is_auth_user_gone('uid1') is True
    finally:
        account_deletion.auth.get_user = original_get_user


def test_is_auth_user_gone_returns_false_for_indeterminate_error(monkeypatch=None):
    """_is_auth_user_gone returns False (fail safe) on non-USER_NOT_FOUND errors."""
    original_get_user = account_deletion.auth.get_user
    account_deletion.auth.get_user = MagicMock(side_effect=Exception('internal error'))
    try:
        assert account_deletion._is_auth_user_gone('uid1') is False
    finally:
        account_deletion.auth.get_user = original_get_user
