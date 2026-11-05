"""Import-light replay contracts; emulator/product imports stay in integration."""

import asyncio
import json
import time
from pathlib import Path

import pytest

from testing.replay_harness.manifest import JSON_SCHEMA, STAGES, load_case, validate_manifest
from testing.replay_harness.report import item_report
from testing.replay_harness.stages.capture_upload import custody_reason
from testing.replay_harness.stages.episodes import EpisodesDriver
from testing.replay_harness.stages.finalization import return_sites
from testing.replay_harness.seed import restore_dates

FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


@pytest.fixture(autouse=True)
def unit_cpu_guard():
    started = time.process_time()
    yield
    assert time.process_time() - started <= 1.00, 'replay titling unit exceeded 1.00s CPU'


@pytest.mark.parametrize(
    'row,chunks,reason',
    [
        ({'record_upload_failed': True, 'record_audio_closed': True}, 1, 'upload_failed'),
        ({'record_upload_sessions': {'a': True}, 'record_audio_closed': True}, 1, 'open_upload_session'),
        ({'record_audio_closed': False}, 1, 'audio_not_closed'),
        ({'record_upload_sessions': {'a': True}}, 0, 'empty_session'),
        ({'record_audio_closed': True}, 0, None),
    ],
)
def test_custody_requires_all_product_barriers(row, chunks, reason):
    assert custody_reason(row, chunks) == reason


def test_capture_schema_v1_empty_expectations_are_observations(tmp_path):
    import jsonschema

    value = load_case(FIXTURES / 'titling-control').manifest.to_dict()
    value.update(tier='C', scrub='owner-tokenized-ciphertext', stages={})
    jsonschema.Draft202012Validator(JSON_SCHEMA).validate(value)
    manifest = validate_manifest(value)
    report = item_report(manifest, [])
    assert report['expectation_met'] is None
    assert report['expectation_verdict'] == 'NOT_SET'
    assert STAGES.index('capture_upload') < STAGES.index('admission')


def test_restore_dates_leaves_ciphertext_opaque():
    value = restore_dates({'created_at': '2026-11-01T00:00:00Z', 'transcript_segments': 'opaque-ciphertext'})
    assert value['created_at'].tzinfo is not None
    assert value['transcript_segments'] == 'opaque-ciphertext'


def test_return_observer_classifies_tuple_return_without_executing_it():
    def example():
        return Structured(), False  # noqa: F821

    assert list(return_sites(example).values()) == ['recovery_undecoded']


def test_episode_boundary_remains_explicitly_unimplemented():
    result = asyncio.run(EpisodesDriver().run(None, None))
    assert result.stage == 'episodes' and result.status == 'not_implemented'


def test_pending_rearm_excludes_dormant_receipts():
    from testing.replay_harness.stages.finalization import pending_rearm

    assert not pending_rearm(None)
    assert not pending_rearm({'version': 3, 'dormant': True})
    assert pending_rearm({'version': 1, 'dormant': False})


def test_loader_refuses_escaping_cassette_symlink(tmp_path):
    import shutil

    case = tmp_path / 'case'
    shutil.copytree(FIXTURES / 'titling-control', case)
    outside = tmp_path / 'outside.json'
    outside.write_text('{}')
    cassette = case / 'cassettes/titling.json'
    cassette.unlink()
    cassette.symlink_to(outside)
    with pytest.raises(ValueError, match='escapes'):
        load_case(case)


def test_emulator_proof_runner_invokes_titling_replay():
    # Workflow path selection for these files lands in a separate PR.
    root = Path(__file__).resolve().parents[3]
    runner = (root / 'backend/scripts/run-emulator-proofs.sh').read_text()
    assert (
        'tests/integration/test_replay_harness_firestore.py \\\n  tests/integration/test_replay_harness_titling_firestore.py'
        in runner
    )


def test_tier_c_notes_cannot_reach_reports_or_stdout(tmp_path, capsys, monkeypatch):
    from testing.replay_harness.report import StageResult, table, write_report

    canary = 'CANARY-uid-8849 private conversation text'
    value = load_case(FIXTURES / 'titling-control').manifest.to_dict()
    value.update(tier='C', notes=canary)
    item = item_report(
        validate_manifest(value), [StageResult('capture_upload', 'pass'), StageResult('titling', 'pass')]
    )
    write_report([item], tmp_path)
    from testing.replay_harness import cli, runner

    async def cases(_directories, **_options):
        return [item]

    monkeypatch.setattr(runner, 'run_cases', cases)
    assert cli.main(['run', '--case', str(FIXTURES / 'titling-control'), '--output', str(tmp_path)]) == 0
    assert 'notes' not in item
    for name in ('report.json', 'report.md', value['id'] + '.json'):
        assert canary not in (tmp_path / name).read_text()
    assert canary not in capsys.readouterr().out


@pytest.mark.parametrize(
    'status,reason,expected',
    [
        ('priority_wait', None, 'priority_wait'),
        ('locked', None, 'locked'),
        ('leased', None, 'leased'),
        ('acked', None, 'already_completed'),
        *[
            ('dropped', name, name)
            for name in (
                'invalid_payload',
                'stale_generation',
                'account_pending_deletion',
                'identity_mismatch',
                'fenced',
                'blocked_byok',
                'missing',
                'not_actionable',
                'completed',
                'dead_letter',
            )
        ],
        ('skipped', 'account_cutover', 'account_cutover'),
        ('completion_conflict', None, 'completion_conflict'),
        ('deferred', None, 'deferred'),
        ('dead_letter', None, 'dead_letter'),
        ('retry', 'persistence_fenced', 'persistence_fenced'),
        ('retry', None, 'worker_retry'),
        ('invalid_payload', None, 'invalid_payload'),
        ('invalid_enrichment_task', None, 'invalid_enrichment_task'),
        ('done', None, None),
        ('dropped', 'uid-private-canary', 'unknown_dropped'),
        ('skipped', 'text-private-canary', 'unknown_skipped'),
        ('private-status', 'private-reason', None),
    ],
)
def test_worker_response_noop_map_is_sanitized(status, reason, expected):
    from types import SimpleNamespace
    from testing.replay_harness.stages.worker_response import read_worker_response, worker_precondition

    response = SimpleNamespace(
        body=json.dumps({'status': status, 'reason': reason, 'content': 'PRIVATE-CANARY'}).encode()
    )
    body = read_worker_response(response)
    assert worker_precondition(body) == expected
    assert 'PRIVATE-CANARY' not in json.dumps(body)
    assert 'private' not in json.dumps(body)


@pytest.mark.parametrize('body', [b'private-canary', b'[]', b'null', b'{"status": ["private-canary"]}'])
def test_malformed_worker_body_is_unknown_without_retaining_content(body):
    from types import SimpleNamespace
    from testing.replay_harness.stages.worker_response import read_worker_response, worker_precondition

    parsed = read_worker_response(SimpleNamespace(body=body))
    assert parsed == {'status': 'unknown', 'reason': None, 'job_status': None}
    assert worker_precondition(parsed) is None
