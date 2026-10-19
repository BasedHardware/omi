"""Hermetic unit tests for backend/database/dream_dirty.py resilience."""

import pytest

from database import dream_dirty


@pytest.fixture
def capture_dirty(monkeypatch):
    calls = []
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'on')
    monkeypatch.setattr(
        dream_dirty,
        'mark_dirty',
        lambda uid, refs, **kwargs: calls.append((uid, refs, kwargs)) or True,
    )
    return calls


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123],
)
def test_notify_ignores_invalid_uid(capture_dirty, bad_uid):
    dream_dirty.notify(bad_uid, [('conversations', 'conv_1')])
    assert capture_dirty == []


@pytest.mark.parametrize(
    'bad_refs',
    [
        [],
        None,
        'conversations/c1',
        [('conversations', '')],
        [('conversations', '   ')],
        [('conversations', 'c/1')],
        [('conversations', 'c..1')],
        [('', 'c1')],
        [('conversations',)],
        [('conversations', 'c1', 'extra')],
        [123],
    ],
)
def test_notify_ignores_malformed_or_unsafe_refs(capture_dirty, bad_refs):
    dream_dirty.notify('user_1', bad_refs)
    assert capture_dirty == []


def test_notify_trims_uid_and_filters_only_valid_refs(capture_dirty):
    dream_dirty.notify(
        '  user_1  ',
        [
            ('  conversations  ', '  conv_1  '),
            ('conversations', '   '),
            ('conversations', 'bad/id'),
            ('action_items', 'task_2'),
        ],
    )
    assert capture_dirty == [('user_1', [('conversations', 'conv_1'), ('action_items', 'task_2')], {})]


def test_after_write_handles_omitted_default_parameter_and_single_parameter_fn(capture_dirty):
    @dream_dirty.after_write('action_items')
    def create_with_default(uid, payload=None):
        return 'task_default_1'

    assert create_with_default('user_1') == 'task_default_1'
    assert capture_dirty == [('user_1', [('action_items', 'task_default_1')], {})]

    capture_dirty.clear()

    @dream_dirty.after_write('action_items')
    def single_arg_fn(uid):
        return 'task_single_1'

    assert single_arg_fn('user_1') == 'task_single_1'
    assert capture_dirty == [('user_1', [('action_items', 'task_single_1')], {})]


def test_after_write_filters_invalid_result_ids_and_trims_valid_ids(capture_dirty):
    @dream_dirty.after_write('action_items')
    def batch_create(uid, items):
        return ['  task_1  ', '', '   ', None, True, 'bad/id', 'task_2']

    res = batch_create('  user_1  ', [{'description': 'a'}])
    assert len(res) == 7
    assert capture_dirty == [('user_1', [('action_items', 'task_1'), ('action_items', 'task_2')], {})]


def test_after_write_skips_when_uid_invalid_or_result_false(capture_dirty):
    @dream_dirty.after_write('conversations')
    def save_conv(uid, data):
        return True

    save_conv('   ', {'id': 'conv_1'})
    save_conv('user/sub', {'id': 'conv_1'})
    assert capture_dirty == []

    @dream_dirty.after_write('conversations')
    def failed_conv(uid, data):
        return False

    assert failed_conv('user_1', {'id': 'conv_1'}) is False
    assert capture_dirty == []


def test_notify_catches_and_records_mark_dirty_exception(monkeypatch):
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'on')

    def _boom(uid, refs, **kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(dream_dirty, 'mark_dirty', _boom)
    # Should not raise
    dream_dirty.notify('user_1', [('conversations', 'conv_1')])
