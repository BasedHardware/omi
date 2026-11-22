"""v3 lane tools: the production overlay for the v3 path and the read-only v3 exporter (synthetic only)."""

import json
from datetime import datetime, timezone
import pytest

from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.stack.overlay import Overlay
from testing.pipeline_lab.stack.runtime_env import DEFAULT_SERVICE, overlay_from_runtime_env, static_mode_names
from testing.pipeline_lab.v3 import prod_export

OWNER = 'synthetic-owner-uid-0001'

RUNTIME_ENV = f"""
schema_version: 2
environments:
  prod:
    cloud_run:
      services:
        backend-sync:
          env:
            CONVERSATIONS_V3: {{value: 'on', category: ops_kill}}
            CONVERSATIONS_V3_STAGE: {{value: beta, category: rollout}}
            CONVERSATIONS_V3_TASKS_QUEUE: {{value: conversations-v3, category: reliability}}
            OMI_SHAPED_AGENT_MODE: {{value: 'on', category: rollout}}
            DREAM_AGENT_UID_ALLOWLIST: {{value: '{OWNER},someone-else', category: rollout}}
            SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST: {{value: 'someone-else', category: rollout}}
            DREAM_AGENT_CANARY_UID: {{value: '', category: rollout}}
"""


@pytest.fixture()
def runtime_env(tmp_path):
    backend = tmp_path / 'backend'
    (backend / 'deploy').mkdir(parents=True)
    (backend / 'config').mkdir()
    (backend / 'config' / 'refactor_modes.py').write_text('# marker: a backend checkout\n')
    (backend / 'utils').mkdir()
    (backend / 'utils' / 'thing.py').write_text(
        "from config.refactor_modes import serving_for\n"
        "def f(uid):\n    return serving_for('NOTES_PACKET_V2_MODE', uid) or serving_for(\"LIFECYCLE_V2_MODE\", uid)\n"
    )
    (backend / 'tests').mkdir()
    (backend / 'tests' / 't.py').write_text("serving_for('TEST_ONLY_MODE', 'u')\n")
    path = backend / 'deploy' / 'runtime_env.yaml'
    path.write_text(RUNTIME_ENV)
    return path


def test_default_service_is_backend_sync_and_v3_switches_are_reported(runtime_env):
    assert DEFAULT_SERVICE == 'backend-sync'
    overlay, report = overlay_from_runtime_env(runtime_env)
    assert report['service'] == 'backend-sync'
    assert overlay['env']['CONVERSATIONS_V3'] == 'on' and overlay['env']['CONVERSATIONS_V3_STAGE'] == 'beta'
    assert 'CONVERSATIONS_V3_TASKS_QUEUE' not in overlay['env']  # endpoints and queues stay lab-owned
    assert report['v3']['CONVERSATIONS_V3_RECORDING_ROTATION'] == '(unset: code default)'
    Overlay.from_mapping(overlay)


def test_every_static_serve_decision_is_pinned(runtime_env):
    (runtime_env.parents[1] / 'config' / 'modes.py').write_text("BOUNDARIES_MODE_ENV = 'EPISODE_BOUNDARIES_MODE'\n")
    names = static_mode_names(runtime_env.parents[1])
    assert names == {'NOTES_PACKET_V2_MODE', 'LIFECYCLE_V2_MODE', 'EPISODE_BOUNDARIES_MODE'}
    overlay, report = overlay_from_runtime_env(runtime_env)
    assert {'NOTES_PACKET_V2_MODE', 'LIFECYCLE_V2_MODE'} <= set(overlay['serving'])
    assert overlay['serving']['NOTES_PACKET_V2_MODE'] is False  # unset mode: shadow, no cohort -> nobody
    assert report['pinned_static'] >= 2


def test_uid_allow_lists_carry_owner_membership_to_the_lab_uid(runtime_env):
    overlay, report = overlay_from_runtime_env(runtime_env, owner_uid=OWNER)
    assert overlay['env']['DREAM_AGENT_UID_ALLOWLIST'] == LAB_UID
    assert overlay['env']['SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'] == ''
    assert report['uid_lists']['DREAM_AGENT_UID_ALLOWLIST'] == 'owner_member'
    assert OWNER not in json.dumps(overlay) and 'someone-else' not in json.dumps(overlay)
    anonymous, report = overlay_from_runtime_env(runtime_env)
    assert anonymous['env']['DREAM_AGENT_UID_ALLOWLIST'] == ''
    assert 'uid_list:DREAM_AGENT_UID_ALLOWLIST' in report['unresolved']
    assert OWNER not in json.dumps(anonymous)


# ---- read-only exporter -------------------------------------------------------------------


class Snap:
    def __init__(self, doc_id, data, exists=True):
        self.id = doc_id
        self._data = data
        self.exists = exists
        self.create_time = datetime(2026, 3, 14, 9, tzinfo=timezone.utc)
        self.update_time = datetime(2026, 3, 14, 10, tzinfo=timezone.utc)

    def to_dict(self):
        return dict(self._data)


class Query:
    def __init__(self, docs):
        self.docs = docs
        self.after = None
        self.cap = None

    def where(self, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.cap = n
        return self

    def start_after(self, doc):
        self.after = doc
        return self

    def stream(self):
        start = self.docs.index(self.after) + 1 if self.after else 0
        return iter(self.docs[start : start + self.cap])


class Client:
    def __init__(self, conversations, leases):
        self.conversations, self.leases = conversations, leases

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def where(self, **kwargs):  # the conversations query
        return Query(self.conversations).where()

    def stream(self):  # the lease collection
        return iter(self.leases)


def test_export_classifies_pages_and_keeps_document_times(tmp_path, monkeypatch):
    snapshot = tmp_path / 'snap'
    snapshot.mkdir()
    (snapshot / 'manifest.json').write_text(
        json.dumps({'window': {'start': '2026-03-14T00:00:00+00:00', 'end': '2026-03-15T00:00:00+00:00'}})
    )
    docs = [Snap(f'rec-{i}', {'recording': True, 'started_at': '2026-03-14T09:00:00+00:00'}) for i in range(3)]
    docs += [Snap('v3-1', {'v3_derived': True}), Snap('legacy-1', {'source': 'omi'})]
    leases = [Snap('builder', {'token': 'secret-token', 'open_id': 'v3-1', 'until': None})]
    monkeypatch.setattr(
        prod_export, 'decode', lambda uid, snap: {**snap.to_dict(), 'id': snap.id, '_create_time': snap.create_time}
    )
    monkeypatch.setattr(prod_export, 'PAGE', 2)
    out = snapshot / 'v3'
    out.mkdir()
    manifest = prod_export.export('uid', Client(docs, leases), snapshot, out)
    assert manifest['counts'] == {'recordings': 3, 'derived': 1, 'other': 1, 'leases': 1, 'unreadable': 0}
    lease = json.loads((out / 'leases.jsonl').read_text())
    assert 'token' not in lease and lease['open_id'] == 'v3-1' and lease['_key'] == 'builder'
    first = json.loads((out / 'recordings.jsonl').read_text().splitlines()[0])
    assert first['_create_time'].startswith('2026-03-14T09')
    assert oct((out / 'recordings.jsonl').stat().st_mode & 0o777) == '0o600'
    assert 'uid' not in json.dumps(manifest['window'])


def test_decode_falls_back_to_raw_without_speech(monkeypatch):
    import types

    fake_store = types.ModuleType('database.conversations_v3')

    def broken(uid, snapshot):
        raise ValueError('bad blob')

    fake_store.decode_row = broken
    monkeypatch.setitem(__import__('sys').modules, 'database.conversations_v3', fake_store)
    import database

    monkeypatch.setattr(database, 'conversations_v3', fake_store, raising=False)
    row = prod_export.decode('uid', Snap('r', {'recording': True, 'transcript_segments': b'zz'}))
    assert row['_export_unreadable'] == 'ValueError' and 'transcript_segments' not in row and row['id'] == 'r'


def test_read_only_fence_refuses_firestore_and_redis_writes():
    from google.cloud.firestore_v1 import document

    with prod_export.read_only_fence():
        with pytest.raises(prod_export.WriteRefused):
            document.DocumentReference.set(object(), {'a': 1})
        import redis

        with pytest.raises(prod_export.WriteRefused):
            redis.Redis.execute_command(object(), 'SET', 'k', 'v')
    assert document.DocumentReference.set is not None


def test_read_only_fence_refuses_deletes_and_pipelines():
    import redis
    from google.cloud.firestore_v1 import client as fs_client
    from google.cloud.storage import bucket as storage_bucket

    with prod_export.read_only_fence():
        with pytest.raises(prod_export.WriteRefused):
            fs_client.Client.recursive_delete(object(), object())
        with pytest.raises(prod_export.WriteRefused):
            storage_bucket.Bucket.delete_blob(object(), 'x')
        with pytest.raises(prod_export.WriteRefused):
            redis.client.Pipeline.execute(object())


def test_output_refuses_a_symlinked_v3_and_never_follows_or_keeps_loose_modes(tmp_path):
    snap = tmp_path / 'snap'
    snap.mkdir()
    (snap / 'manifest.json').write_text('{}')
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (snap / 'v3').symlink_to(elsewhere)
    with pytest.raises(SystemExit):
        prod_export.resolve_output(snap, allowed_root=tmp_path.parent)
    (snap / 'v3').unlink()
    out = prod_export.resolve_output(snap, allowed_root=tmp_path.parent)
    loose = out / 'recordings.jsonl'
    loose.write_text('old')
    loose.chmod(0o644)
    assert prod_export._write_jsonl(loose, [{'a': 1}]) == 1
    assert oct(loose.stat().st_mode & 0o777) == '0o600'
    target = tmp_path / 'target.jsonl'
    target.write_text('keep')
    (out / 'derived.jsonl').symlink_to(target)
    with pytest.raises(OSError):
        prod_export._write_jsonl(out / 'derived.jsonl', [{'a': 1}])
    assert target.read_text() == 'keep'


def test_git_probe_fails_closed(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    (repo / '.git').mkdir(parents=True)
    assert prod_export._inside_git_worktree(repo / 'snap')

    def broken(*args, **kwargs):
        raise OSError('no git')

    monkeypatch.setattr(prod_export.subprocess, 'run', broken)
    assert prod_export._inside_git_worktree(tmp_path / 'plain')


def test_output_and_guard_are_refused_outside_the_rules(tmp_path):
    with pytest.raises(SystemExit):
        prod_export.resolve_output(tmp_path / 'snap')  # not under /Volumes/Ephemeral
    snap = tmp_path / 'snap'
    snap.mkdir()
    (snap / 'manifest.json').write_text('{}')
    with pytest.raises(SystemExit):
        prod_export.resolve_output(tmp_path / 'elsewhere', allowed_root=tmp_path.parent)  # no manifest
    out = prod_export.resolve_output(snap, allowed_root=tmp_path.parent)
    assert out == snap.resolve() / 'v3' and oct(out.stat().st_mode & 0o777) == '0o700'
    guard = tmp_path / 'guard.py'
    guard.write_text('def owner_uid(path):\n    return "x"\n')
    with pytest.raises(SystemExit):
        prod_export.load_guard(guard)  # no load_secret
    guard.write_text('def owner_uid(path):\n    return "x"\n\ndef load_secret(path):\n    return None\n')
    assert prod_export.load_guard(guard).owner_uid('f') == 'x'


def test_owner_uid_file_must_be_private(tmp_path):
    from testing.pipeline_lab.cli import CliError, read_private_value

    path = tmp_path / 'uid.txt'
    path.write_text(OWNER + '\n')
    path.chmod(0o644)
    with pytest.raises(CliError):
        read_private_value(path)
    path.chmod(0o600)
    assert read_private_value(path) == OWNER
    with pytest.raises(CliError):
        read_private_value(tmp_path / 'missing')


def describe(env):
    return {
        'metadata': {'name': 'backend-sync'},
        'spec': {'template': {'spec': {'containers': [{'env': env}]}}},
        'status': {'traffic': [{'revisionName': 'backend-sync-abc-1', 'percent': 100}]},
    }


def test_filter_live_env_drops_secrets_and_scrubs_owner_uid():
    from testing.pipeline_lab.stack.runtime_env import filter_live_env

    live = filter_live_env(
        describe(
            [
                {'name': 'MEMORY_MODE', 'value': 'v3'},
                {'name': 'ADMIN_API_KEY', 'value': 'plain-secret-value'},
                {'name': 'DB_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 's', 'key': 'k'}}},
                {'name': 'FAIR_USE_EXEMPT_UIDS', 'value': f'{OWNER},someone-else'},
                {'name': 'CAPTURE_JEV_SHADOW_UID_ALLOWLIST', 'value': 'someone-else'},
                {'name': 'ODD_SETTING', 'value': f'prefix-{OWNER}'},
                {'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'a' * 40},
            ]
        ),
        OWNER,
    )
    text = json.dumps(live)
    assert 'plain-secret-value' not in text and OWNER not in text and 'someone-else' not in text
    assert live['env']['FAIR_USE_EXEMPT_UIDS'] == LAB_UID and live['env']['CAPTURE_JEV_SHADOW_UID_ALLOWLIST'] == ''
    assert live['env']['ODD_SETTING'] == f'prefix-{LAB_UID}' and live['dropped_secret_or_ref'] == 2
    assert live['release_sha'] == 'a' * 40 and live['traffic'][0]['percent'] == 100
    with pytest.raises(ValueError):
        filter_live_env(describe([]), '')


def test_live_env_adds_ops_and_live_only_values(runtime_env):
    from testing.pipeline_lab.stack.runtime_env import filter_live_env

    live = filter_live_env(
        describe(
            [
                {'name': 'CONVERSATIONS_V3', 'value': 'on'},
                {'name': 'MEMORY_MODE', 'value': 'v3'},
                {'name': 'OMI_SHAPED_AGENT_MODE', 'value': 'off'},
                {'name': 'FAIR_USE_EXEMPT_UIDS', 'value': OWNER},
                {'name': 'SYNC_TASKS_QUEUE', 'value': 'sync'},
            ]
        ),
        OWNER,
    )
    overlay, report = overlay_from_runtime_env(runtime_env, live_env=live)
    assert overlay['env']['MEMORY_MODE'] == 'v3' and overlay['env']['OMI_SHAPED_AGENT_MODE'] == 'off'
    assert overlay['env']['FAIR_USE_EXEMPT_UIDS'] == LAB_UID  # the lab uid keeps the owner's membership
    assert 'SYNC_TASKS_QUEUE' not in overlay['env']  # still lab-owned
    assert report['live']['added'] == 3 and report['live']['overridden'] == 1
    assert report['live_names']['overridden'] == ['OMI_SHAPED_AGENT_MODE']


def test_stage_keys_carry_the_selected_pipeline(tmp_path):
    from types import SimpleNamespace

    from testing.pipeline_lab import keys
    from testing.pipeline_lab.orchestrator import run_pipeline_kind

    store = SimpleNamespace(day_dir=lambda day_id: tmp_path / day_id)
    v3_on = {'env': {'CONVERSATIONS_V3': 'on'}}
    assert run_pipeline_kind(store, v3_on, 'd1') == 'classic'  # no recordings on the day
    (tmp_path / 'd1' / 'v3').mkdir(parents=True)
    (tmp_path / 'd1' / 'v3' / 'recordings.jsonl').write_text('')
    assert run_pipeline_kind(store, v3_on, 'd1') == 'v3'
    assert run_pipeline_kind(store, {**v3_on, 'model_config': {'pipeline': 'classic'}}, 'd1') == 'classic'
    assert run_pipeline_kind(store, {'model_config': {'pipeline': 'v3'}}, 'd2') == 'refused'
    key = lambda pipeline: keys.stage_key('discard', backend_tree='t', inputs={'pipeline': pipeline})
    assert key('v3') != key('classic')


def test_a_failed_decrypt_during_export_never_logs_the_owner_uid(caplog):
    import logging

    from utils.encryption import decrypt

    uid = 'owner-uid-7f3a'
    caplog.set_level(logging.ERROR)
    with prod_export.redact_uid(uid):
        assert decrypt('bm90LWNpcGhlcnRleHQ=', uid) == 'bm90LWNpcGhlcnRleHQ='  # malformed: returned as is
        logging.getLogger('anything').error('plain %s', uid)
    assert caplog.records, 'the failed decrypt should still be logged'
    assert all(uid not in r.getMessage() for r in caplog.records)
    assert any('<owner>' in r.getMessage() for r in caplog.records)
