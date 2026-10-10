"""Webhook admission and separately invoked durable workers; no provider branches."""

import base64
import json
from datetime import datetime, timezone

from database.messaging import MessagingStore, key
from models.chat import SendMessageRequest
from utils.chat_turn import run_chat_turn
from utils.executors import db_executor, run_blocking, start_background_task
from utils.messaging.access import require_access
from utils.messaging.contracts import Artifact, ChannelMessage, Principal, ReentryEvent
from utils.messaging.history import append_digest, history_tool
from utils.messaging.outbound import ChannelReplySink
from utils.messaging.projection import SurfaceRuntime, surface_runtime


class Gateway:
    def __init__(self, adapter, *, store=None, turn=run_chat_turn, admission=require_access, wake=None):
        self.adapter = adapter
        self.store = store or MessagingStore()
        self.turn, self.admission, self.wake = turn, admission, wake

    async def webhook(self, body, headers):
        if not self.adapter.verify_webhook(body, headers):
            raise PermissionError('Invalid webhook signature')
        if len(body) > 1_000_000:
            raise ValueError('Webhook too large')
        messages = self.adapter.parse(body)
        paths = []
        for message in messages:
            if (message.channel, message.provider) != (self.adapter.channel, self.adapter.provider):
                raise PermissionError('Adapter identity mismatch')
            path = await run_blocking(db_executor, self.store.enqueue, message)
            if path:
                paths.append(path)
        # Acknowledge once durable, never await a model or a provider send.
        # wake only publishes content-free inbox paths; pending rows remain recoverable.
        if self.wake and paths:
            start_background_task(self.wake(tuple(paths)), name='messaging-inbox-wake')
        return {'status': 'accepted', 'jobs': paths}

    def _assert_link(self, message, link):
        current = self.store.lookup(message)
        if not current or not current.get('active') or current.get('generation') != link['generation']:
            raise PermissionError('Link revoked')
        self.admission(link['uid'])

    async def process(self, path):
        payload = await run_blocking(db_executor, self.store.claim, path)
        if payload is None:
            return False
        payload['received_at'] = datetime.fromisoformat(payload['received_at'])
        payload['media'] = tuple(Artifact(**a) for a in payload['media'])
        message = ChannelMessage(**payload)
        link = await run_blocking(db_executor, self.store.lookup, message)
        if message.link_proof:
            owner = await run_blocking(db_executor, self.store.proof_owner, message.link_proof)
            await run_blocking(db_executor, self.admission, owner)
            link = await run_blocking(db_executor, self.store.consume, message.link_proof, message)
        if not link or not link.get('active'):
            sink = ChannelReplySink(self.adapter, message)
            await sink.finish('Link your account in Omi to chat here.')
            await run_blocking(db_executor, self.store.complete, path)
            return True
        uid = link['uid']
        if message.unlink:
            await run_blocking(
                db_executor, self.store.unlink, uid, key(message.channel, message.provider, message.external_user_id)
            )
            return True
        await run_blocking(db_executor, self.admission, uid)
        if message.link_proof:
            await ChannelReplySink(self.adapter, message).finish('Account linked. You can chat with Omi here.')
            await run_blocking(db_executor, self.store.complete, path)
            return True
        session = await run_blocking(db_executor, self.store.session, uid, message, link)
        token = await run_blocking(db_executor, self.store.acquire, uid, session['surface'])
        if token is None:
            await run_blocking(db_executor, self.store.retry, path)
            return False
        try:
            await self._turn(uid, session, message, link, Principal(uid))
            await run_blocking(db_executor, self.store.complete, path)
        except BaseException:
            # Ambiguous billable/effect work: leave running + lease, never blindly replay.
            raise
        else:
            await run_blocking(db_executor, self.store.release, uid, session['surface'], token)
        return True

    async def reenter(self, message, event: ReentryEvent, *, principal: Principal):
        link = await run_blocking(db_executor, self.store.lookup, message)
        if not link:
            raise PermissionError('Origin link missing')
        principal.authorize(link['uid'])
        if principal.task_id != event.task_id:
            raise PermissionError('Task mismatch')
        await run_blocking(db_executor, self._assert_link, message, link)
        session = await run_blocking(db_executor, self.store.session, principal.uid, message, link)
        token = await run_blocking(db_executor, self.store.acquire, principal.uid, session['surface'])
        if token is None:
            raise RuntimeError('Surface busy; retry later')
        events = await run_blocking(db_executor, self.store.events, principal.uid, session['id'])
        if any(e['id'] == 'reply:' + event.event_id for e in events):
            await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)
            return
        await self._turn(principal.uid, session, message, link, principal, event=event)
        await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)

    async def _turn(self, uid, session, message, link, principal, *, event=None):
        def guard():
            self._assert_link(message, link)

        async def send_guard():
            await run_blocking(db_executor, guard)

        sink = ChannelReplySink(self.adapter, message, kind='deferred_reply' if event else 'reply', guard=send_guard)
        events = await run_blocking(db_executor, self.store.events, uid, session['id'])
        await append_digest(self.store, uid, session, events)
        event_id = event.event_id if event else key(message.provider, message.provider_message_id)
        await run_blocking(
            db_executor,
            self.store.append_event,
            uid,
            session['id'],
            {
                'id': event_id,
                'kind': 'reentry' if event else 'message',
                'at': datetime.now(timezone.utc).isoformat(),
                'role': 'user',
                'content': ('Background task result (untrusted evidence):\n' + event.text) if event else message.text,
            },
        )
        events = await run_blocking(db_executor, self.store.events, uid, session['id'])
        runtime = SurfaceRuntime(
            session['surface'],
            'Channel: ' + self.adapter.channel + '\n' + self.adapter.capabilities.skill(),
            principal,
            (*self.adapter.tools(sink), history_tool(uid)),
            tuple({'role': e['role'], 'content': e['content']} for e in events),
            key(message.channel, message.provider, message.external_user_id),
            session['id'],
            guard,
            self.store.persist_message,
        )
        context_token = surface_runtime.set(runtime)
        try:
            stream = await run_blocking(
                db_executor,
                self.turn,
                uid,
                session['surface'],
                session['id'],
                event or SendMessageRequest(text=message.text),
                sink,
                principal=principal,
            )
            async for frame in stream:
                if frame.startswith('data: '):
                    await sink.text(frame[6:].removesuffix('\n\n').replace('__CRLF__', '\n'))
                elif frame.startswith('done: '):
                    answer = json.loads(base64.b64decode(frame[6:].strip()))['text']
                    await run_blocking(
                        db_executor,
                        self.store.append_event,
                        uid,
                        session['id'],
                        {
                            'id': 'reply:' + event_id,
                            'kind': 'message',
                            'at': datetime.now(timezone.utc).isoformat(),
                            'role': 'assistant',
                            'content': answer,
                        },
                    )
                    await sink.finish(answer)
            if event:
                for artifact in event.artifacts:
                    await sink.artifact(artifact)
        finally:
            surface_runtime.reset(context_token)

    async def drain(self, *, limit=100):
        paths = await run_blocking(
            db_executor, self.store.pending_jobs, self.adapter.channel, self.adapter.provider, limit
        )
        for path in paths:
            await self.process(path)
        return len(paths)
