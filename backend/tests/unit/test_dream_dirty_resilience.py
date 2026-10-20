import pytest

from database import dream_dirty


@pytest.fixture
def marked(monkeypatch):
    calls = []
    monkeypatch.setattr(dream_dirty, 'mode', lambda: 'on')
    monkeypatch.setattr(dream_dirty, 'mark_dirty', lambda uid, refs, **kw: calls.append((uid, refs)) or True)
    return calls


def test_omitted_default_second_argument(marked):
    @dream_dirty.after_write('memories')
    def write(uid, data={'id': 'm1'}):
        return True

    assert write('u1') is True
    assert marked == [('u1', [('memories', 'm1')])]


def test_fewer_than_two_parameters_does_not_raise(marked):
    @dream_dirty.after_write('memories')
    def write(uid):
        return 'ok'

    assert write('u1') == 'ok'
    assert marked == []


def test_no_parameters_does_not_raise(marked):
    @dream_dirty.after_write('memories')
    def write():
        return 'ok'

    assert write() == 'ok'
    assert marked == []


def test_action_item_result_ids_are_filtered(marked):
    @dream_dirty.after_write('action_items')
    def write(uid, data):
        return [None, True, '', '  ', '../x', 'a/b', 'a\\b', 'bad\x00id', 'x' * 129, 5, ' ok ']

    write('u1', [{'id': 'ignored'}])
    assert marked == [('u1', [('action_items', 'ok')])]


@pytest.mark.parametrize('uid', ['', '  ', 'a/b', 'a\\b', '..', 'a..b', 'a\nb', 'u' * 129, None, 5, True])
def test_notify_drops_unsafe_uid(marked, uid):
    dream_dirty.notify(uid, [('c', 'd')])
    assert marked == []


@pytest.mark.parametrize(
    'refs',
    [None, 'cd', [('c',)], [('c', 'd', 'e')], [('', 'd')], [('c', ' ')], [('c', '../d')], [('c', None)], [1, 2]],
)
def test_notify_drops_malformed_refs(marked, refs):
    dream_dirty.notify('u1', refs)
    assert marked == []


def test_notify_strips_and_keeps_valid_refs(marked):
    dream_dirty.notify(' u1 ', [(' c ', ' d '), ('c', '../bad'), ['c2', 'd2']])
    assert marked == [('u1', [('c', 'd'), ('c2', 'd2')])]
