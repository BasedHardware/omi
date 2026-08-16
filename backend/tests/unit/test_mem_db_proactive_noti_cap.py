"""Regression: the in-memory proactive-notification cache must stay bounded.

database.mem_db.proactive_noti_sent_at maps "<uid>:<app_id>" -> (sent_ts, expiry_ts). An expired
entry is deleted only when its OWN key is read again (get_proactive_noti_sent_at), so keys for
churned users or uninstalled apps are never revisited and accumulate for the process lifetime (the
repo's rule requires module-level dicts to cap or TTL). set_proactive_noti_sent_at now sweeps expired
entries and caps the map.
"""

import pytest

import database.mem_db as mem_db


@pytest.fixture(autouse=True)
def _clear():
    mem_db.proactive_noti_sent_at.clear()
    yield
    mem_db.proactive_noti_sent_at.clear()


def test_expired_entries_are_swept_when_over_cap(monkeypatch):
    monkeypatch.setattr(mem_db, "_MAX_PROACTIVE_NOTI_ENTRIES", 5)
    # All already expired (negative ttl); before the fix these would never be evicted (never re-read).
    for i in range(20):
        mem_db.set_proactive_noti_sent_at(f"u{i}", app_id="a", ts=1, ttl=-100)

    assert len(mem_db.proactive_noti_sent_at) <= 5


def test_cap_holds_even_when_all_entries_are_live(monkeypatch):
    monkeypatch.setattr(mem_db, "_MAX_PROACTIVE_NOTI_ENTRIES", 5)
    for i in range(20):
        mem_db.set_proactive_noti_sent_at(f"u{i}", app_id="a", ts=i, ttl=3600)

    assert len(mem_db.proactive_noti_sent_at) <= 5


def test_get_still_returns_live_and_none_for_expired():
    mem_db.set_proactive_noti_sent_at("u", app_id="a", ts=42, ttl=3600)
    assert mem_db.get_proactive_noti_sent_at("u", "a") == 42

    mem_db.set_proactive_noti_sent_at("u", app_id="b", ts=7, ttl=-100)
    assert mem_db.get_proactive_noti_sent_at("u", "b") is None
