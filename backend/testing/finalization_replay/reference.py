"""Call the real Python admission, claim, finalizer and acknowledgement."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch


async def _finalize(state, intent, claim, trigger):
    from database import conversation_finalization_jobs as jobs
    from utils.conversations import finalizer, lifecycle

    job_id = intent['job_id']
    generation = intent['dispatch_generation']
    epoch = claim['lease_epoch']
    disposition = await finalizer.finalize_persisted_conversation(
        state.uid,
        state.cid,
        finalization_job_id=job_id,
        dispatch_generation=generation,
        lease_epoch=epoch,
        trigger=trigger,
    )
    if disposition.value == 'fenced':
        if not lifecycle.complete_fenced_finalization(job_id, generation, epoch):
            raise RuntimeError('Python fenced acknowledgement refused')
    elif disposition.value in {'completed', 'discarded'}:
        if not jobs.mark_finalization_completed(job_id, generation, epoch):
            raise RuntimeError('Python completion acknowledgement refused')
        return 'completed'
    return disposition.value


def _run(state):
    from database import conversation_finalization_jobs as jobs
    from utils.conversations import lifecycle
    from utils.conversations.processing_trigger import ProcessingTrigger

    trigger = ProcessingTrigger(state.case.get('trigger', 'capture_end'))
    intent = lifecycle.request_finalization(state.uid, state.cid, has_byok_keys=False, trigger=trigger)
    job_id = intent['job_id']
    if job_id is None:
        return 'not_found' if intent['status'] == 'missing' else intent['status']
    if state.case.get('repeat'):
        again = lifecycle.request_finalization(state.uid, state.cid, has_byok_keys=False, trigger=trigger)
        if again['job_id'] != job_id:
            raise RuntimeError('Python duplicate admitted a different job')
    claim = jobs.claim_finalization_job(job_id, intent['dispatch_generation'], count_worker_claim=True)
    if claim['status'] != 'claimed':
        return claim['status']
    return asyncio.run(_finalize(state, intent, claim, trigger))


def run_reference(state, stack):
    from models.structured import Structured
    from testing.listen_pusher_stack import finalizer_leaves as leaves
    from utils.conversations import finalizer, process_conversation as processing
    from utils.conversations.memory_extraction_telemetry import (
        ConversationMemoryExtractionResult,
        PATH_CANONICAL,
        source_for_conversation,
    )
    from utils.encryption import encrypt

    def notes(_uid, _language, conversation, **_kwargs):
        words = ' '.join(segment.text for segment in conversation.transcript_segments).split()
        if len(words) < state.case.get('min_words', 1):
            return Structured(), True
        return Structured(**state.notes), False

    def memories(uid, conversation, **_kwargs):
        protection = conversation.data_protection_level
        for index, content in enumerate(state.memories):
            stored = encrypt(content, uid) if protection == 'enhanced' else content
            state.memory(f'{state.cid}-{index}', stored, protection)
        return ConversationMemoryExtractionResult(
            count=len(state.memories),
            source=source_for_conversation(conversation),
            path=PATH_CANONICAL,
        )

    def vector(_uid, conversation, **_kwargs):
        state.vector(conversation.structured.overview)
        return True

    stack.enter_context(patch.object(processing, '_get_structured', notes))
    stack.enter_context(patch.object(processing, '_extract_memories_canonical', memories))
    stack.enter_context(patch.object(processing, 'trigger_conversation_apps', leaves._offline_noop))
    stack.enter_context(patch.object(processing, 'assign_conversation_to_folder', leaves._offline_folder_assignment))
    stack.enter_context(patch.object(processing, 'save_structured_vector', vector))
    stack.enter_context(patch.object(processing, '_save_action_items', leaves._offline_noop))
    stack.enter_context(patch.object(processing, 'update_goal_progress', leaves._offline_noop))
    stack.enter_context(patch.object(processing, 'conversation_created_webhook', leaves._offline_noop_async))
    stack.enter_context(patch.object(processing.conversations_db, 'create_audio_files_from_chunks', return_value=[]))
    stack.enter_context(patch.object(finalizer, 'save_structured_vector', vector))
    _record_webhooks(state, stack)
    return _run(state)


def _record_webhooks(state, stack):
    """Run the real integration fanout against an in-process transport."""
    from httpx import Response
    from utils import app_integrations

    apps = [
        SimpleNamespace(
            id=app,
            uid=state.uid,
            enabled=True,
            triggers_on_conversation_creation=lambda: True,
            external_integration=SimpleNamespace(webhook_url=f'https://replay.invalid/apps/{app}'),
        )
        for app in state.apps
    ]

    class Transport:
        async def post(self, url, *, json, headers, **_kwargs):
            app = url.split('?', 1)[0].rsplit('/', 1)[1]
            state.webhook(app, headers.get('X-Omi-Idempotency-Key'), json)
            return Response(200, json={})

    def target(url):
        # The injected transport never resolves or connects to this fixture URL.
        return url, {'headers': {}, 'extensions': {}}

    stack.enter_context(patch.object(app_integrations, 'get_available_apps', return_value=apps))
    stack.enter_context(patch.object(app_integrations, 'is_app_webhook_disabled', return_value=False))
    stack.enter_context(patch.object(app_integrations, 'safe_request_target', target))
    stack.enter_context(patch.object(app_integrations, 'get_webhook_client', return_value=Transport()))
