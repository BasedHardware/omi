"""Real result commit, ordered log, native projection and enrichment follow-up.

Scheduler.complete is the production fenced result transaction. OrderedMerge
commits that result to the owner log; Projector.persist and ProjectionFollowups
then call ProjectionStore.mark_enrichment. Only result-blob reading and queue /
playback / client transport leaves are local. No outbox is fabricated here.
"""

from contextlib import ExitStack
import json
import os
from unittest.mock import patch


async def commit_late_result(case, environment):
    from database.batch_pipeline_intake import admit
    from database import batch_pipeline_projection_claim as claims
    from utils.batch_pipeline.contracts import WorkItem, WorkResult, Priority, ProjectionBinding
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.projection import Projector
    from utils.batch_pipeline.projection_followup import ProjectionFollowups
    from utils.enrichment import outbox
    from utils.executors import db_executor, run_blocking

    if case.manifest.tier != 'S':
        raise ValueError('synthetic late-result admission requires tier S')
    path = case.directory / 'cassettes' / 'batch_result.json'
    if case.directory not in path.resolve().parents:
        raise ValueError('result cassette escapes case directory')
    payload = json.loads(path.read_text())
    uid, cid = environment.replay_uid, environment.replay_cid
    row = environment.conversation_ref.get().to_dict()
    now = environment.clock.time()
    sid = 'synthetic-late-result'
    item = WorkItem(
        sid,
        uid,
        row['started_at'].timestamp(),
        'gs://replay-staged/synthetic-audio#1',
        180,
        Priority.FRESH,
        conversation_id=cid,
        privacy_generation=0,
    )
    binding = ProjectionBinding(
        uid,
        'synthetic-result-job',
        'synthetic-result-content',
        (sid,),
        target_conversation_id=cid,
        data_protection_level='standard',
        record_origin=True,
        native_record=True,
    )
    target = environment.store.client.collection(outbox.COLLECTION).document(outbox.key(uid, cid))
    environment.replay_documents.append(target)
    wakes = []
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                os.environ,
                {
                    'BATCH_PIPELINE_ENABLED': 'true',
                    'BATCH_PIPELINE_PERCENT': '100',
                    'BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED': 'true',
                    'SYNC_BACKFILL_ROUTING_ENABLED': 'false',
                    'SYNC_TASKS_QUEUE': 'replay-enrichment',
                    'SYNC_TASKS_HANDLER_URL': 'https://replay.invalid/v2/sync-jobs/run',
                    'SYNC_TASKS_INVOKER_SA': 'replay@example.invalid',
                },
            )
        )
        stack.enter_context(patch.object(claims, '_redis_client', lambda: environment.redis))
        stack.enter_context(patch.object(outbox, '_enqueue', lambda value: wakes.append(value)))
        admitted = await run_blocking(
            db_executor, admit, environment.store, [item], binding, now, namespace=environment.store.namespace
        )
        queue = Scheduler(environment.store)
        leases = await run_blocking(db_executor, queue.pull, now)
        lease = next(lease for lease in leases if lease.item.segment_id == sid)
        committed = await run_blocking(
            db_executor, queue.complete, WorkResult(sid, 'gs://replay-staged/synthetic-result#1'), lease.token, now + 1
        )
        merged = await run_blocking(db_executor, OrderedMerge(environment.store).commit_next, uid, now + 2)
        projector = Projector(
            environment.store,
            lambda *_: payload,
            publish=lambda *_: None,
            playback=lambda *_: None,
            clock=lambda: now + 3,
        )
        await run_blocking(db_executor, projector.persist, sid)
        await ProjectionFollowups(projector).run(sid)
    entry = environment.store.run(lambda tx: tx.get('results', sid))
    return {
        'admitted': admitted.get('outcome') == 'batch',
        'result_committed': committed,
        'result_log_committed': merged is not None,
        'projection_state': (entry.get('projection') or {}).get('state'),
        'enrichment_wakes': len(wakes),
        'outbox_created': target.get().exists,
    }


async def replay_enrichment(environment):
    """Deliver a persisted real outbox token at its recorded due time, no vendor I/O."""
    from utils.enrichment import outbox
    from utils.batch_pipeline.enrichment import run_enrichment
    from utils.executors import postprocess_executor, run_blocking

    uid, cid = environment.replay_uid, environment.replay_cid
    target = environment.store.client.collection(outbox.COLLECTION).document(outbox.key(uid, cid))
    row = target.get().to_dict()
    if not row or row.get('dormant'):
        return None
    token = row.get('task_token')
    if not isinstance(token, str) or len(token) != 32:
        return 'missing_task_binding'
    return await run_blocking(
        postprocess_executor,
        run_enrichment,
        target.id,
        token,
        now=max(environment.clock.time(), float(row.get('due_at', 0))) + 1,
    )
