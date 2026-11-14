"""The late-member re-arm has its own kill switch, independent of the THRIFT perf flag."""

from config import episodes as episode_config
from utils.episodes import late_member

CLOSED = {'status': 'closed', 'composed_at': 'composed'}


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(late_member.composer, 'schedule_for_conversation', lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.delenv(episode_config.EPISODE_COMPOSE_LATE_ATTACH_ENABLED_ENV, raising=False)
    return calls


def test_rearm_survives_the_thrift_cost_switch_going_off(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setenv(episode_config.EPISODE_COMPOSER_THRIFT_ENV, 'off')
    late_member.joined('u', 'c-late', {}, CLOSED, object())
    # THRIFT is a cost control; turning it off must not restore the class-7 gap.
    assert calls


def test_kill_switch_stops_the_rearm(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setenv(episode_config.EPISODE_COMPOSE_LATE_ATTACH_ENABLED_ENV, 'off')
    late_member.joined('u', 'c-late', {}, CLOSED, object())
    assert not calls


def test_live_or_uncomposed_episode_is_left_to_its_own_compose(monkeypatch):
    calls = _capture(monkeypatch)
    late_member.joined('u', 'c-late', {}, {'status': 'live'}, object())
    late_member.joined('u', 'c-late', {}, {'status': 'closed'}, object())
    late_member.joined('u', 'c-late', {}, None, object())
    assert not calls
