"""Hermetic Redis SCAN / Firestore CAS backfill coverage."""

import json
from types import SimpleNamespace

import fakeredis
from google.api_core.exceptions import FailedPrecondition

from scripts import backfill_conversation_owner_uid as backfill


class Client:
    def __init__(self, docs):
        self.docs = docs
        self.writes = []
        self.conflict = False

    def collection_group(self, name):
        assert name == 'conversations'
        return self

    def where(self, *, filter):
        assert filter.field_path == 'id'
        self.cid = filter.value
        return self

    def select(self, fields):
        return self

    def limit(self, n):
        assert n == 2
        return self

    def stream(self):
        result = []
        for path, data in self.docs.items():
            if data.get('id') == self.cid:
                ref = SimpleNamespace(
                    path=path, update=lambda patch, option, path=path: self.update(path, patch, option)
                )
                result.append(SimpleNamespace(reference=ref, to_dict=lambda data=data: dict(data), update_time=1))
        return result[:2]

    def write_option(self, *, last_update_time):
        return last_update_time

    def update(self, path, patch, option):
        assert option == 1
        if self.conflict:
            raise FailedPrecondition('concurrent unshare')
        self.docs[path].update(patch)
        self.writes.append((path, patch))


def setup_store():
    redis = fakeredis.FakeRedis()
    redis.set('memories-visibility:cid', 'owner')
    client = Client({'users/owner/conversations/cid': {'id': 'cid', 'visibility': 'shared'}})
    return redis, client


def test_idempotent_rescan_and_source_keys_preserved(tmp_path):
    redis, client = setup_store()
    checkpoint = tmp_path / 'checkpoint.json'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True)
    assert result['written'] == 1 and result['complete']
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True, rescan=True)
    assert result['written'] == 0 and len(client.writes) == 1
    assert redis.get('memories-visibility:cid') == b'owner'
    assert json.loads(checkpoint.read_text())['reserved'] == 1


def test_conflicts_quarantined_without_modifying_docs(tmp_path):
    redis, client = setup_store()
    redis.set('memories-visibility:cid', 'wrong-redis-owner')
    checkpoint = tmp_path / 'checkpoint.json'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True)
    assert result['quarantined'] == 1 and not client.writes
    report = json.loads(checkpoint.with_suffix('.json.quarantine.jsonl').read_text())
    assert report['reason'] == 'missing_ambiguous_or_parent_mismatch'
    redis.set('memories-visibility:cid', 'owner')
    client.docs['users/owner/conversations/cid']['owner_uid'] = 'wrong-field'
    backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True, rescan=True)
    assert not client.writes
    assert 'owner_or_id_mismatch' in checkpoint.with_suffix('.json.quarantine.jsonl').read_text()


def test_daily_budget_and_pending_page_resume(tmp_path):
    redis, client = setup_store()
    redis.set('memories-visibility:second', 'owner')
    client.docs['users/owner/conversations/second'] = {'id': 'second', 'visibility': 'public'}
    checkpoint = tmp_path / 'checkpoint.json'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True, daily_limit=1, today='2026-10-16')
    assert result['budget_exhausted'] and len(client.writes) == 1
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True, daily_limit=1, today='2026-10-16')
    assert result['budget_exhausted'] and len(client.writes) == 1
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True, daily_limit=1, today='2026-10-17')
    assert result['complete'] and len(client.writes) == 2


def test_dry_run_and_deleted_or_private_docs_are_not_written(tmp_path):
    redis, client = setup_store()
    checkpoint = tmp_path / 'checkpoint.json'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint)
    assert result['eligible'] == 1 and not client.writes and not checkpoint.exists()
    client.docs['users/owner/conversations/cid']['deleted'] = True
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True)
    assert result['written'] == 0


def test_concurrent_unshare_cas_leaves_key_for_revalidation(tmp_path):
    redis, client = setup_store()
    client.conflict = True
    checkpoint = tmp_path / 'checkpoint.json'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True)
    assert result['contended'] and not client.writes
    state = json.loads(checkpoint.read_text())
    assert state['pending'] == ['memories-visibility:cid'] and state['reserved'] == 1
    client.conflict = False
    client.docs['users/owner/conversations/cid']['visibility'] = 'private'
    result = backfill.run_backfill(redis, client, checkpoint=checkpoint, apply=True)
    assert result['complete'] and not client.writes


def test_ambiguous_id_quarantines(tmp_path):
    redis, client = setup_store()
    client.docs['users/other/conversations/cid'] = {'id': 'cid', 'visibility': 'shared'}
    result = backfill.run_backfill(redis, client, checkpoint=tmp_path / 'checkpoint.json', apply=True)
    assert result['quarantined'] == 1 and not client.writes


def test_requested_budget_cannot_exceed_ten_thousand(tmp_path):
    redis, client = setup_store()
    checkpoint = tmp_path / 'checkpoint.json'
    checkpoint.write_text(
        json.dumps(
            {
                'cursor': 0,
                'pending': ['memories-visibility:cid'],
                'complete': False,
                'day': '2026-10-16',
                'reserved': 10_000,
            }
        )
    )
    result = backfill.run_backfill(
        redis, client, checkpoint=checkpoint, apply=True, daily_limit=50_000, today='2026-10-16'
    )
    assert result['budget_exhausted'] and not client.writes


def test_nested_non_user_conversation_path_is_quarantined(tmp_path):
    redis, client = setup_store()
    redis.set('memories-visibility:cid', 'owner/nested/path')
    client.docs = {'users/owner/nested/path/conversations/cid': {'id': 'cid', 'visibility': 'shared'}}
    result = backfill.run_backfill(redis, client, checkpoint=tmp_path / 'checkpoint.json', apply=True)
    assert result['quarantined'] == 1 and not client.writes
