"""Scheduled synthetic path through dirty admission, real dream lanes and encrypted report."""

import asyncio
import logging
from dataclasses import replace

from config.dream_agent import Caps, canary_uid, mode
from database import dream_canary, dream_store, review_store
from utils import dream_agent, dream_transport
from utils.executors import db_executor, run_blocking
from utils.dream_metrics import CANARY

logger = logging.getLogger(__name__)
DEADLINE_SECONDS = 85


class CanaryFailure(Exception):
    pass


async def check():
    uid = canary_uid()
    stage = 'enqueue'
    passed = False
    error = 'none'
    consecutive = 0
    progress = {}
    try:
        async with asyncio.timeout(DEADLINE_SECONDS):
            if not uid or mode() == 'off':
                raise CanaryFailure('disabled')
            await run_blocking(db_executor, dream_canary.seed, uid)
            if not await run_blocking(db_executor, dream_store.dirty_count, uid):
                raise CanaryFailure('not_enqueued')
            stage = 'admit'
            # Schema bytes dominate the cap; only 256 completion tokens per lane.
            # Allow 48 half-hour checks plus retries, sharing the global ceiling.
            caps = replace(
                Caps.from_env(), tokens=min(16000, Caps.from_env().tokens), passes=96, edits=1, completion_tokens=256
            )
            report = await dream_agent.run_pass(uid, caps=caps, canary=True, timeout_seconds=65, progress=progress)
            progress.clear()
            if not report.get('run_id'):
                raise CanaryFailure('not_admitted')
            stage = 'model'
            if report.get('status') != 'complete' or set(report.get('model_lanes', [])) != {
                dream_transport.TRIAGE_LANE,
                dream_transport.MAIN_LANE,
            }:
                error = report.get('error_type') or 'CanaryFailure'
                raise CanaryFailure('model_incomplete')
            stage = 'report'
            doc = await run_blocking(db_executor, dream_store.own_run, uid, report['run_id'])
            decoded = await run_blocking(db_executor, review_store.decode_doc, uid, doc)
            if (
                not decoded
                or decoded.get('source', {}).get('status') != 'complete'
                or doc.get('mode') != 'shadow'
                or doc.get('tokens', 0) <= 0
            ):
                raise CanaryFailure('report_missing')
            passed = True
    except Exception as exc:
        stage = progress.get('stage', stage)
        if error == 'none':
            error = type(exc).__name__
    try:
        async with asyncio.timeout(3):
            consecutive = await run_blocking(db_executor, dream_canary.record_result, passed)
    except Exception as exc:
        passed, error = False, type(exc).__name__
    status = 'pass' if passed else 'fail'
    CANARY.labels(status, stage).inc()
    logger.info(
        'Dream canary status=%s stage=%s error_type=%s consecutive_failures=%d', status, stage, error, consecutive
    )
    return {'status': status, 'stage': stage, 'error_type': error, 'consecutive_failures': consecutive}
