"""Regression test: a corrupt Redis sync-job blob must not 500 the sync-status poll.

database.sync_jobs reads job documents from Redis with json.loads. The redis_db layer is
documented as fail-open (all errors caught and logged, requests proceed), and the fenced
mutation paths in this same module already guard json.loads with
except (TypeError, ValueError, json.JSONDecodeError). get_sync_job and update_sync_job did
not, so a corrupt or legacy sync_job:{id} blob raised JSONDecodeError out of the status
poll / update path. Both now return None (unknown job) on unparseable data, matching the
sibling fenced paths and the fail-open contract.
"""

import database.sync_jobs as sync_jobs


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        return self._value


def test_get_sync_job_returns_none_on_corrupt_blob(monkeypatch):
    monkeypatch.setattr(sync_jobs, "r", _FakeRedis(b"{not valid json"))

    assert sync_jobs.get_sync_job("job-1") is None


def test_get_sync_job_parses_valid_blob(monkeypatch):
    monkeypatch.setattr(sync_jobs, "r", _FakeRedis(b'{"id": "job-2", "status": "processing"}'))

    assert sync_jobs.get_sync_job("job-2") == {"id": "job-2", "status": "processing"}


def test_update_sync_job_returns_none_on_corrupt_blob(monkeypatch):
    monkeypatch.setattr(sync_jobs, "r", _FakeRedis(b"{not valid json"))

    assert sync_jobs.update_sync_job("job-3", {"status": "completed"}) is None
