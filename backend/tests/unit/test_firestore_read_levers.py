import pytest

from config import firestore_read_levers as levers


@pytest.fixture(autouse=True)
def _clear_cache():
    levers._parse.cache_clear()
    yield
    levers._parse.cache_clear()


def test_default_off(monkeypatch):
    monkeypatch.delenv(levers.ENV_KEY, raising=False)
    assert levers.lever_percent('singleton_loops') == 0
    assert not levers.lever_enabled('singleton_loops', 'pod-1')


def test_full_rollout_needs_no_key(monkeypatch):
    monkeypatch.setenv(levers.ENV_KEY, '{"singleton_loops": 100}')
    assert levers.lever_enabled('singleton_loops')
    assert not levers.lever_enabled('listen_poll', 'uid')


def test_partial_rollout_is_stable_and_proportional(monkeypatch):
    monkeypatch.setenv(levers.ENV_KEY, '{"listen_poll": 5}')
    hits = [levers.lever_enabled('listen_poll', f'uid-{i}') for i in range(4000)]
    assert 0.03 < sum(hits) / len(hits) < 0.07
    assert hits == [levers.lever_enabled('listen_poll', f'uid-{i}') for i in range(4000)]
    assert not levers.lever_enabled('listen_poll')


@pytest.mark.parametrize(
    'raw', ['not json', '[1]', '{"listen_poll": 101}', '{"listen_poll": true}', '{"listen_poll": "50"}']
)
def test_malformed_values_are_off(monkeypatch, raw):
    monkeypatch.setenv(levers.ENV_KEY, raw)
    assert levers.lever_percent('listen_poll') == 0


def test_unknown_names(monkeypatch):
    monkeypatch.setenv(levers.ENV_KEY, '{"bogus": 100, "listen_poll": 100}')
    assert levers.lever_enabled('listen_poll')
    with pytest.raises(ValueError):
        levers.lever_percent('bogus')
