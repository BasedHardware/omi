"""Import-light replay contracts; emulator/product imports stay in integration."""

import asyncio
import json
from pathlib import Path

import pytest

from testing.replay_harness.manifest import JSON_SCHEMA, STAGES, load_case, validate_manifest
from testing.replay_harness.report import item_report
from testing.replay_harness.stages.capture_upload import custody_reason
from testing.replay_harness.stages.episodes import EpisodesDriver
from testing.replay_harness.stages.finalization import return_sites
from testing.replay_harness.seed import restore_dates

FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


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


def test_existing_ci_includes_titling_paths_and_same_proof_invocation():
    import yaml

    root = Path(__file__).resolve().parents[3]
    workflow = yaml.load((root / '.github/workflows/backend-emulator-proofs.yml').read_text(), Loader=yaml.BaseLoader)
    for trigger in ('push', 'pull_request'):
        paths = workflow['on'][trigger]['paths']
        assert 'backend/utils/conversations/**' in paths
        assert 'backend/services/conversation_finalization.py' in paths
        assert 'backend/routers/conversation_finalization.py' in paths
        assert 'backend/tests/integration/test_replay_harness_titling_firestore.py' in paths
    runner = (root / 'backend/scripts/run-emulator-proofs.sh').read_text()
    assert (
        'tests/integration/test_replay_harness_firestore.py \\\n  tests/integration/test_replay_harness_titling_firestore.py'
        in runner
    )
