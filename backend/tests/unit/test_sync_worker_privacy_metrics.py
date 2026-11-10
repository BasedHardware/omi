"""Child privacy measurements survive normal exit, SIGKILL and subsequent jobs."""

import asyncio
import os
from pathlib import Path
import signal
import sys

from prometheus_client.parser import text_string_to_metric_families
import pytest

from utils.sync.worker_privacy_metrics import WorkerPrivacyMetrics

CHILD = """
from database import privacy_check_metrics as metrics
from prometheus_client import Counter
from types import SimpleNamespace
import sys
metrics.called('batch')
metrics.decision('batch')
metrics.walked()
metrics.read_snapshot('batch', SimpleNamespace(get=lambda: SimpleNamespace(exists=True)))
with metrics.mode_scope('shadow'):
    metrics.called('batch')
    metrics.decision('batch')
    metrics.walked()
    metrics.read_snapshot('batch', SimpleNamespace(get=lambda: SimpleNamespace(exists=False)))
metrics.compare('batch', 'allow', 'allow')
metrics.compare('batch', 'account_deleted', 'allow')
metrics.memo_result('batch', 'hit')
metrics.negative_lookup('conversations', 'shadow', 'mismatch')
Counter('unrelated_total', 'Not privacy').inc()
print('ready', flush=True)
sys.stdin.read()
"""


def samples(metrics):
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(metrics.render().decode())
        for sample in family.samples
    }


@pytest.mark.parametrize('killed', [False, True])
async def test_child_counters_survive_reaping_without_double_count_or_file_growth(killed):
    metrics = WorkerPrivacyMetrics()
    for attempt in range(1, 3):
        env = metrics.begin_job()
        directory = Path(env['PROMETHEUS_MULTIPROC_DIR'])
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            '-c',
            CHILD,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            start_new_session=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        try:
            assert await asyncio.wait_for(process.stdout.readline(), 15) == b'ready\n'
            before = samples(metrics)
            assert before[('privacy_check_calls_total', (('family', 'batch'), ('mode', 'live')))] == attempt
            assert before[('privacy_check_calls_total', (('family', 'batch'), ('mode', 'shadow')))] == attempt
            assert before[('privacy_shadow_checks_total', (('family', 'batch'), ('result', 'match')))] == attempt
            assert before[('privacy_memo_requests_total', (('family', 'batch'), ('result', 'hit')))] == attempt
            assert (
                before[('privacy_decision_mismatch_total', (('family', 'batch'), ('reason', 'stale_allow')))] == attempt
            )
            assert before[('privacy_conversations_walked_total', (('mode', 'live'),))] == attempt
            assert before[('privacy_conversations_walked_total', (('mode', 'shadow'),))] == attempt
            assert (
                before[
                    (
                        'privacy_check_reads_total',
                        (('family', 'batch'), ('mode', 'live'), ('plan_group', 'unattributed'), ('result', 'hit')),
                    )
                ]
                == attempt
            )
            assert (
                before[
                    (
                        'privacy_check_reads_total',
                        (('family', 'batch'), ('mode', 'shadow'), ('plan_group', 'unattributed'), ('result', 'miss')),
                    )
                ]
                == attempt
            )
            assert {name for name, _ in before} == {
                'privacy_checks_total',
                'privacy_check_calls_total',
                'privacy_check_reads_total',
                'privacy_conversations_walked_total',
                'privacy_decision_mismatch_total',
                'privacy_shadow_checks_total',
                'privacy_memo_requests_total',
                'privacy_negative_lookup_total',
            }
            assert (
                before[
                    (
                        'privacy_negative_lookup_total',
                        (('collection', 'conversations'), ('mode', 'shadow'), ('result', 'mismatch')),
                    )
                ]
                == attempt
            )
            if killed:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.stdin.close()
            await asyncio.wait_for(process.wait(), 15)
        finally:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await asyncio.wait_for(process.wait(), 15)
            metrics.finish_job()
        assert samples(metrics) == before
        assert not directory.exists()
    assert 'PROMETHEUS_MULTIPROC_DIR' not in os.environ


async def test_supervisor_wires_child_counters_to_metrics_endpoint(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from utils.sync import worker_runtime

    app = worker_runtime.create_app()
    client = AsyncMock()
    client.call.return_value = {'accepted': True}
    runtime = worker_runtime.Runtime(client)
    app.state.runtime = runtime
    responses = []

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:

        async def launch(env):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                '-c',
                CHILD,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                start_new_session=True,
                cwd=Path(__file__).resolve().parents[2],
            )
            try:
                assert await asyncio.wait_for(process.stdout.readline(), 15) == b'ready\n'
                responses.append(await http.get('/metrics'))
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                await asyncio.wait_for(process.wait(), 15)
                raise
            return process

        monkeypatch.setattr(worker_runtime, 'launch_job', launch)
        lease = {'payload': {'uid': 'synthetic', 'job_id': 'job', 'sequencer_epoch': 1}, 'token': 'synthetic'}
        await asyncio.wait_for(runtime.execute(lease), 20)
        responses.append(await http.get('/metrics'))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].content == responses[1].content
    assert b'privacy_shadow_checks_total{family="batch",result="match"} 1.0' in responses[1].content
    assert b'privacy_decision_mismatch_total{family="batch",reason="stale_allow"} 1.0' in responses[1].content
    assert runtime.privacy_metrics._directory is None
    assert client.call.call_args.args[0] == 'complete'


def test_memo_ineligible_counter_survives_isolated_job_exits():
    """Luna r1 P2 on #24666: the parent only folds counters named in COUNTERS."""
    from utils.sync.worker_privacy_metrics import COUNTERS

    assert 'privacy_memo_ineligible' in COUNTERS


@pytest.mark.parametrize('killed', [False, True])
async def test_live_child_rollout_values_are_scraped_and_disappear_on_exit(killed):
    metrics = WorkerPrivacyMetrics()
    env = metrics.begin_job()
    env['ROLLOUT_POD_TEMPLATE_HASH'] = 'synthetic-pod-hash'
    env.pop('K_REVISION', None)
    child = """
from database import rollout_cohorts as store
from utils.rollout import runtime_percent as rp
import sys
rp._background_submitter = lambda fn: fn()
rp._cache = rp._RampCache(lambda: store.normalize_ramp_document({
    'schema_version': 1, 'revision': 5, 'envs': {'prod': {
        'percents': {'batch-pipeline': 23, 'new-owner-cell1': 17},
        'legacy_sync': 'on', 'locked_by': None}}}))
rp.configure_runtime_percent()
assert rp.runtime_percent('batch-pipeline', env_default=0) == 23
print('ready', flush=True)
sys.stdin.read()
"""
    env['OMI_ENV_STAGE'] = 'prod'
    env.pop('OMI_DEPLOYMENT', None)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        '-c',
        child,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        start_new_session=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 30) == b'ready\n'
        rows = [s for f in text_string_to_metric_families(metrics.render().decode()) for s in f.samples]
        values = {s.labels['name']: s.value for s in rows if s.name == 'omi_runtime_percent'}
        assert len(values) == 6
        assert values['batch-pipeline'] == 23 and values['new-owner-cell1'] == 17
        for row in rows:
            assert row.labels['revision'] == 'synthetic-pod-hash'
            assert row.labels['pid'] == str(process.pid)
        if killed:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.stdin.close()
        await asyncio.wait_for(process.wait(), 15)
    finally:
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await asyncio.wait_for(process.wait(), 15)
        metrics.finish_job()
    assert not metrics.render().strip()  # dead consumers never leave adoption evidence
