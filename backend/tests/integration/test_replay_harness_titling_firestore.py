"""Real custody closure and durable titling worker, with local provider cassettes."""

import asyncio
from dataclasses import replace
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures'


@pytest.fixture(autouse=True)
def require_emulator():
    if not os.getenv('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')


def test_capture_and_titling_cases(tmp_path):
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import table, write_report

    items = asyncio.run(run_cases(sorted(p for p in FIXTURES.iterdir() if p.name.startswith(('capture-', 'titling-')))))
    write_report(items, tmp_path)
    print('\n' + table(items))
    assert all(item['expectation_met'] for item in items), table(items)
    by_id = {item['item']: item for item in items}
    control = by_id['titling-control']['stages'][-1]
    assert control['details']['llm_calls'] == 1
    assert control['details']['final_job_status'] == 'completed'
    assert control['details']['has_title']
    minimum = by_id['titling-minimum-length']['stages'][0]
    assert minimum['details']['llm_calls'] == 0
    assert minimum['observations'] == [{'reason': 'titling:precondition_skipped:minimum_length'}]
    dedupe = by_id['titling-dedupe']['stages'][0]
    assert dedupe['details']['checkpoint_preparation_calls'] == 1
    assert dedupe['details']['llm_calls'] == 0
    assert {'reason': 'titling:precondition_skipped:dedupe'} in dedupe['observations']
    seal = by_id['capture-seal-control']['stages'][0]
    assert seal['details']['audio_closed'] and seal['details']['seal_refusal'] is None
    assert by_id['capture-open-upload-session']['stages'][0]['details']['seal_refusal'] == 'producer_pending'
    assert by_id['capture-upload-failed']['stages'][0]['details']['seal_refusal'] == 'upload_failed'


def test_wp2_metadata_only_capture_seeds_without_decryption(monkeypatch):
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case, validate_manifest
    from testing.replay_harness.stages.capture_upload import CaptureUploadDriver
    from testing.replay_harness.stages.finalization import TitlingDriver
    from utils import encryption

    def refuse(*a, **kw):
        raise AssertionError('metadata replay attempted decryption')

    monkeypatch.setattr(encryption, 'decrypt', refuse)
    case = load_case(FIXTURES / 'titling-completed-without-title')
    corpus = {
        **case.corpus,
        'source': 'firestore-owner-ciphertext',
        'seed_blobs': [],
        'conversation': {**case.corpus['conversation'], 'transcript_segments': 'opaque-ciphertext'},
    }
    manifest = validate_manifest({**case.manifest.to_dict(), 'tier': 'C', 'stages': {}})
    case = replace(case, manifest=manifest, corpus=corpus)

    async def run():
        with replay_environment() as environment:
            capture = await CaptureUploadDriver().run(case, environment)
            titling = await TitlingDriver().run(case, environment)
            refs = list(environment.replay_documents)
            client = environment.store.client
            assert capture.status == 'pass'
            assert titling.reason == 'titling:completed_without_title'
        assert all(not ref.get().exists for ref in refs)

    asyncio.run(run())


def test_real_late_result_projection_rearms_and_status_only_cannot_pass(monkeypatch, tmp_path):
    from database.batch_pipeline_projection import ProjectionStore
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.stages.finalization import TitlingDriver

    async def drive(name):
        with replay_environment() as environment:
            return await TitlingDriver().run(load_case(FIXTURES / name), environment)

    # The synthetic completed-without-title seed has no committed result/arrival yet.
    stopped = asyncio.run(drive('titling-completed-without-title'))
    assert stopped.reason == 'titling:completed_without_title'
    real_mark = ProjectionStore.mark_enrichment

    def status_only(store, segment, binding, now, canonical, language, **kwargs):
        store.client.collection('users').document(binding.owner_id).collection('conversations').document(
            canonical
        ).update({'status': 'completed', 'finalization_status': 'completed'})

    with monkeypatch.context() as patcher:
        patcher.setattr(ProjectionStore, 'mark_enrichment', status_only)
        broken = asyncio.run(drive('titling-late-result-control'))
    assert broken.reason == 'titling:completed_without_title'
    assert broken.details['late_result']['result_committed']
    assert broken.details['late_result']['result_log_committed']
    assert not broken.details['has_title'] and broken.details['final_job_status'] == 'completed'
    assert broken.details['llm_calls'] == 0

    def rearm(store, *args, **kwargs):
        return real_mark(store, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(ProjectionStore, 'mark_enrichment', rearm)
        healed = asyncio.run(drive('titling-late-result-control'))
    assert healed.status == 'pass'
    assert healed.details['has_title'] and healed.details['final_job_status'] == 'completed'
    assert healed.details['llm_calls'] == 1
    assert healed.details['late_result']['projection_state'] == 'ready'
    assert healed.details['late_result']['enrichment_wakes'] == 1
    assert healed.details['enrichment_delivery'] == 'processed'
    assert healed.details['enrichment_settled']

    from dataclasses import asdict
    import json

    proof = {'no_arrival': asdict(stopped), 'status_only': asdict(broken), 'real_rearm': asdict(healed)}
    (tmp_path / 'late-result-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('P1 proof: no arrival=STOP; status-only result path=STOP; real re-arm=PASS')


def test_recovery_guard_enabled_reports_its_real_skip_branches():
    from copy import deepcopy
    from unittest.mock import patch
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.stages.finalization import TitlingDriver

    async def drive(name, minimum=False):
        case = load_case(FIXTURES / name)
        if minimum:
            corpus = deepcopy(case.corpus)
            corpus['conversation']['transcript_segments'][0]['text'] = 'We should review this project again next week.'
            case = replace(case, corpus=corpus)
        with replay_environment() as environment, patch.dict(
            os.environ,
            {
                'LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED': 'true',
                'NOTES_SHORT_CLIP_FLOOR': 'false',
                'NOTES_PACKET_V2_MODE': 'off',
            },
        ):
            return await TitlingDriver().run(case, environment)

    discarded = asyncio.run(drive('titling-recovery-rule-discard'))
    assert discarded.reason == 'titling:precondition_skipped:recovery_rule_discard'
    assert discarded.details['llm_calls'] == 0
    minimum = asyncio.run(drive('titling-recovery-minimum', minimum=True))
    assert minimum.status == 'pass' and minimum.details['llm_calls'] == 0
    assert {'reason': 'titling:precondition_skipped:recovery_minimum'} in minimum.observations


def test_completed_projection_cannot_substitute_for_missing_job():
    from copy import deepcopy
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.stages.finalization import TitlingDriver

    case = load_case(FIXTURES / 'titling-control')
    corpus = deepcopy(case.corpus)
    corpus['finalization_jobs'] = {}
    corpus['conversation'].update(finalization_status='completed', structured={'title': 'Already titled'})
    case = replace(case, corpus=corpus)

    async def drive():
        with replay_environment() as environment:
            return await TitlingDriver().run(case, environment)

    result = asyncio.run(drive())
    assert result.reason == 'titling:precondition_skipped:finalization_missing'
    assert result.details['initial_job_status'] == 'missing'


@pytest.mark.parametrize(
    'body,label',
    [
        ({'status': 'priority_wait'}, 'priority_wait'),
        ({'status': 'locked'}, 'locked'),
        ({'status': 'leased'}, 'leased'),
        ({'status': 'done'}, 'worker_done_without_title'),
        ({'status': 'dropped', 'reason': 'stale_generation'}, 'stale_generation'),
        ({'status': 'skipped', 'reason': 'account_cutover'}, 'account_cutover'),
        ({'status': 'retry', 'reason': 'persistence_fenced'}, 'persistence_fenced'),
    ],
)
def test_driver_uses_sanitized_noop_body(monkeypatch, body, label):
    from fastapi.responses import JSONResponse
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.stages.finalization import TitlingDriver

    async def drive():
        with replay_environment() as environment:
            from routers import conversation_finalization as worker

            async def respond(*args, **kwargs):
                if body.get('reason') == 'account_cutover':
                    for document in environment.replay_documents:
                        if document.parent.id == 'conversation_finalization_jobs':
                            document.update({'status': 'completed'})
                return JSONResponse(content={**body, 'private': 'CANARY-private-uid-text'})

            with monkeypatch.context() as patcher:
                patcher.setattr(worker, 'run_listen_finalization_job', respond)
                return await TitlingDriver().run(load_case(FIXTURES / 'titling-control'), environment)

    result = asyncio.run(drive())
    assert result.reason == 'titling:precondition_skipped:' + label
    assert 'CANARY-private-uid-text' not in repr(result)
