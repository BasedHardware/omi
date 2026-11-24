"""Call the real Python admission, claim, finalizer and acknowledgement."""

from __future__ import annotations

import asyncio
from contextvars import copy_context
from hashlib import sha256
from threading import local
from unittest.mock import patch
from urllib.parse import urlsplit


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
        final_attempt=state.case.get('final_attempt', False),
    )
    if disposition.value == 'fenced':
        if not lifecycle.complete_fenced_finalization(job_id, generation, epoch):
            raise RuntimeError('Python fenced acknowledgement refused')
    elif disposition.value in {'completed', 'discarded'}:
        if not jobs.mark_finalization_completed(job_id, generation, epoch):
            raise RuntimeError('Python completion acknowledgement refused')
    return disposition.value


def _run(state):
    from database import conversation_finalization_jobs as jobs
    from utils.conversations import lifecycle
    from utils.conversations.processing_trigger import ProcessingTrigger

    from utils.byok import get_byok_keys

    has_keys = bool(get_byok_keys())
    trigger = ProcessingTrigger(state.case.get('trigger', 'capture_end'))
    intent = lifecycle.request_finalization(state.uid, state.cid, has_byok_keys=has_keys, trigger=trigger)
    job_id = intent['job_id']
    if job_id is None:
        return 'not_found' if intent['status'] == 'missing' else intent['status']
    state.admitted = {'job_id': job_id, 'fanout_key': intent['fanout_key'], 'own_key': intent['requires_byok']}
    if state.case.get('repeat'):
        again = lifecycle.request_finalization(state.uid, state.cid, has_byok_keys=has_keys, trigger=trigger)
        if again['job_id'] != job_id:
            raise RuntimeError('Python duplicate admitted a different job')
    claim = jobs.claim_finalization_job(
        job_id, intent['dispatch_generation'], count_worker_claim=True, allow_byok=has_keys
    )
    status = claim['status']
    if status == 'claimed':
        status = asyncio.run(_finalize(state, intent, claim, trigger))
    state.queue_fanout_key = jobs.get_finalization_job(job_id).get('fanout_key')
    return status


def run_reference(state, stack, url):
    from database import redis_db, vector_db
    from models.users import WebhookType
    from utils import app_integrations, webhooks
    from utils.byok import set_validated_byok_keys
    from utils.conversations import process_conversation as processing

    def pin(target):
        parsed = urlsplit(target)
        if parsed.scheme != 'http' or parsed.netloc != urlsplit(url).netloc or not parsed.path.startswith('/receive/'):
            raise ValueError('webhook must target the replay HTTP receiver')
        return target, {'headers': {}, 'extensions': {}}

    stack.enter_context(patch.object(app_integrations, 'safe_request_target', pin))
    stack.enter_context(patch.object(webhooks, 'safe_request_targets', lambda target: [pin(target)]))
    # Replace the vendor SDK at its network boundary. Production computes metadata and records.
    vectors = VectorReceiver(state, vector_db.embeddings)
    stack.enter_context(patch.object(vector_db, 'index', vectors))
    stack.enter_context(patch.object(vector_db, 'embeddings', vectors))

    futures = []
    submit = processing.submit_with_context

    def track(executor, fn, *args, **kwargs):
        future = submit(executor, fn, *args, **kwargs)
        futures.append(future)
        return future

    stack.enter_context(patch.object(processing, 'submit_with_context', track))
    for app in state.apps:
        redis_db.enable_app(state.uid, app)
    if state.apps:
        redis_db.set_user_preferred_app(state.uid, state.apps[0])
        hook = WebhookType.memory_created
        redis_db.set_user_webhook_db(state.uid, hook, f'{url}/receive/developer-created')
        redis_db.enable_user_webhook_db(state.uid, hook)

    def invoke():
        if state.user.get().to_dict()['byok']['active']:
            set_validated_byok_keys({'openai': 'replay-only-vendor-key'}, state.uid)
        return _run(state)

    try:
        return copy_context().run(invoke)
    finally:
        for future in futures:
            future.result(timeout=12)


class VectorReceiver:
    """Record the outgoing vector operation after the real owner routing and shaping."""

    def __init__(self, state, embeddings):
        self.state = state
        self.embeddings = embeddings
        self._inputs = local()

    def __getattr__(self, name):
        return getattr(self.embeddings, name)

    def embed_documents(self, texts, *args, **kwargs):
        vectors = self.embeddings.embed_documents(texts, *args, **kwargs)
        self._inputs.pending = (list(texts), vectors)
        return vectors

    def query(self, **_kwargs):
        return {'matches': []}

    def upsert(self, *, vectors, namespace, **_kwargs):
        pending = getattr(self._inputs, 'pending', None)
        self._inputs.pending = None
        if namespace == 'ns4' and pending is not None:
            texts, produced = pending
            if len(texts) == len(vectors) and [record['values'] for record in vectors] == produced:
                for record, text in zip(vectors, texts):
                    self.state.task_embedding_inputs.setdefault(record['id'], []).append(sha256(text.encode()).hexdigest())
        for record in vectors:
            if record['id'] == f'{self.state.uid}-{self.state.cid}':
                self.state.vector(self.state.cid)
                kind = 'python_vector_payload'
            else:
                kind = 'other_vectors'
            self.state.effects.setdefault(kind, []).append({'namespace': namespace, 'record': record})
        return {'upserted_count': len(vectors)}, 200, {'x-pinecone-request-lsn': '1'}
