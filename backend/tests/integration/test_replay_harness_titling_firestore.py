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


def test_late_result_commit_and_projection_enqueue_are_distinct():
    from testing.replay_harness.env import replay_environment
    from testing.replay_harness.manifest import load_case
    from testing.replay_harness.seed import seed_case
    from testing.replay_harness.stages.finalization import pending_rearm
    from database.outbox_firestore import FirestoreEnrichmentOutbox
    from utils.enrichment import outbox

    with replay_environment() as environment:
        conversation = seed_case(load_case(FIXTURES / 'titling-completed-without-title'), environment)
        uid, cid = environment.replay_uid, environment.replay_cid
        target = environment.store.client.collection('sync_reprocess_outbox').document(outbox.key(uid, cid))
        environment.replay_documents.append(target)

        # A result document is data, not a wakeup. This exercises persistence
        # only; a complete worker -> projector arrival remains outside WP4.
        def commit_result(tx):
            tx.put('jobs', 'synthetic-late-result', {'owner_id': uid, 'conversation_id': cid})
            tx.put('results', 'synthetic-late-result', {'result': {'outcome': 'ok'}})

        environment.store.run(commit_result)
        assert not target.get().exists
        assert conversation.get().to_dict()['finalization_status'] == 'completed'
        wakes = []
        producer = FirestoreEnrichmentOutbox(environment.store.client, create_wake=lambda *args: wakes.append(args))
        # The exact producer called by mark_enrichment, after its projection
        # receipt decides enrichment_required. Queue transport alone is local.
        producer.enqueue(
            outbox.key(uid, cid),
            uid,
            {'conversation_id': cid, 'language': 'en'},
            environment.clock.time(),
            now=environment.clock.time(),
            snapshot_summary=True,
        )
        assert pending_rearm(target.get().to_dict()) and len(wakes) == 1
        assert conversation.get().to_dict()['finalization_status'] == 'completed'


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
