"""Stage an exact-file alias with its own durable audio; no language/ASR calls."""

from dataclasses import replace
import time

from google.api_core.exceptions import NotFound

from database.batch_pipeline_source_reuse import lookup
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline import source_reuse
from utils.executors import db_executor, storage_executor, run_blocking


async def stage_alias(store, artifacts, item, unit, context):
    if not item.source_reuse_key:
        return None
    candidate = await run_blocking(db_executor, lookup, store, item, time.time())
    if candidate is None:
        source_reuse.observe('uncovered_tail', item.duration_seconds)
        return None
    canonical_job = candidate['job']
    canonical = WorkItem(**{key: canonical_job[key] for key in WorkItem.__dataclass_fields__ if key in canonical_job})
    try:
        # Physical/authenticated availability, not just a Firestore URI. The
        # contents remain private and are never copied to the alias marker.
        await run_blocking(storage_executor, artifacts.load_result, canonical, canonical_job['result']['result_uri'])
    except NotFound:
        source_reuse.observe('alias_refusal')
        return None
    item = replace(
        item, source_alias_of=candidate['segment_id'], source_conversation_ids=tuple(candidate['dependencies'])
    )
    # Always retain the newly uploaded audio before admitting this alias.
    frozen = with_context(unit.wav, {**context, 'source_reuse_key': item.source_reuse_key})
    try:
        uri = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
    except Exception:
        source_reuse.observe('custody_failure')
        raise
    staged = replace(item, audio_uri=uri, requires_compute_admission=False)
    result_uri = await run_blocking(
        storage_executor,
        artifacts.persist_result,
        staged,
        {
            'source_alias_version': 1,
            'source_reuse_key': item.source_reuse_key,
            'canonical_segment_id': candidate['segment_id'],
        },
    )
    return staged, {'segment_id': candidate['segment_id'], 'result_uri': result_uri}
