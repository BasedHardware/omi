"""Webhook admission and separately invoked durable workers; no provider branches."""

import asyncio
import base64
import logging
import json
import time
from dataclasses import replace
from datetime import datetime, timezone

from database.messaging import MessagingStore
from utils.messaging.identity import key
from models.chat import SendMessageRequest
from utils.chat_turn import run_chat_turn
from utils.executors import db_executor, postprocess_executor, run_blocking, start_background_task
from utils.messaging.access import require_access
from utils.messaging.contracts import Artifact, ChannelMessage, InboundAttachment, Principal, ReentryEvent
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
        payload['attachments'] = tuple(InboundAttachment(**a) for a in payload.get('attachments', ()))
        message = ChannelMessage(**payload)
        if hasattr(self.adapter, 'admitted'):
            await self.adapter.admitted(message)
        if hasattr(self.adapter, 'acknowledge'):
            try:
                await self.adapter.acknowledge(message)
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'Messaging callback acknowledgement failed error_type=%s', type(error).__name__
                )
        link = await run_blocking(db_executor, self.store.lookup, message)
        if message.link_proof:
            try:
                owner = await run_blocking(db_executor, self.store.proof_owner, message.link_proof)
                await run_blocking(db_executor, self.admission, owner)
                link = await run_blocking(db_executor, self.store.consume, message.link_proof, message)
            except PermissionError:
                # Same fixed reply as an unknown sender. Do not distinguish a bad,
                # expired, or unauthorized proof.
                await ChannelReplySink(self.adapter, message).finish('Link your account in Omi to chat here.')
                await run_blocking(db_executor, self.store.complete, path)
                return True
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

        async def guard():
            await run_blocking(db_executor, self._assert_link, message, link)

        sink = ChannelReplySink(self.adapter, message, guard=guard)
        typing_stop = asyncio.Event()
        typing_task = None
        session = token = None
        started = time.monotonic()
        try:
            # First action after authenticated admission, before session/history,
            # digest, media or model setup. Typing is best-effort, never turn authority.
            await _try_typing(sink)
            logging.getLogger(__name__).info(
                'Messaging phase=typing provider=%s elapsed_ms=%.1f',
                self.adapter.provider,
                (time.monotonic() - started) * 1000,
            )
            typing_task = start_background_task(_refresh_typing(sink, typing_stop), name='messaging-typing')
            session = await run_blocking(db_executor, self.store.session, uid, message, link)
            token = await run_blocking(db_executor, self.store.acquire, uid, session['surface'])
            if token is None:
                await run_blocking(db_executor, self.store.retry, path)
                return False
            if message.command == 'help':
                await sink.finish(
                    'Chat with your Omi agent about your memories, tasks and files. '
                    'Supported actions have their own confirmation and Undo control. '
                    'Use /unlink to disconnect. Messages are used only to serve your chat.'
                )
            elif message.command == 'undo':
                # Adapters with inline controls require an action-specific ID;
                # old generic buttons/text cannot reverse an unrelated later action.
                if hasattr(self.adapter, 'receipt_buttons') and not message.undo_receipt_id:
                    await sink.finish(
                        'Use Undo on the specific action confirmation. This old control has no action attached.'
                    )
                else:
                    # The inverse owns its durable receipt claim. It must not
                    # monopolize the chat lease while canonical privacy cleanup
                    # scans derived projections. Never replay a running inverse.
                    start_background_task(self._undo_action(uid, session, message, sink), name='messaging-undo-action')
            else:
                if link.get('voice_notes', True) is False and any(item.voice for item in message.attachments):
                    message = replace(
                        message, attachments=tuple(item for item in message.attachments if not item.voice)
                    )
                if (
                    link.get('voice_notes', True) is False
                    and not message.text.strip()
                    and not message.attachments
                    and not message.media
                ):
                    await sink.finish('Voice notes are turned off for this chat. Send a text message instead.')
                else:
                    if hasattr(self.adapter, 'prepare'):
                        message = await self.adapter.prepare(message, uid, session, guard)
                    await self._turn(uid, session, message, link, Principal(uid), sink=sink)
            await run_blocking(db_executor, self.store.complete, path)
        except Exception as error:
            # The coroutine has unwound. Fence this job against replay (including
            # ambiguous delivery/inverses), but release the surface for a NEW turn.
            logging.getLogger(__name__).error(
                'Messaging turn failed provider=%s error_type=%s', self.adapter.provider, type(error).__name__
            )
            try:
                await sink.finish(
                    'I couldn’t finish that request. Please try again. Check any action confirmation before repeating a write.'
                )
            except Exception as send_error:
                logging.getLogger(__name__).error(
                    'Messaging error reply failed error_type=%s', type(send_error).__name__
                )
            await run_blocking(db_executor, self.store.complete, path)
        finally:
            typing_stop.set()
            if typing_task:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
            try:
                await _try_typing(sink, False)
            except PermissionError:
                pass  # revoked links must still release settled turn ownership
            # Cancellation can leave executor/provider work alive. Retain fencing
            # on process shutdown; ordinary settled errors never strand the chat.
            current_task = asyncio.current_task()
            if token and session is not None and (current_task is None or not current_task.cancelling()):
                await run_blocking(db_executor, self.store.release, uid, session['surface'], token)
        return True

    async def _undo_action(self, uid, session, message, sink):
        from utils.messaging.undo import UndoStore

        try:
            result = await run_blocking(
                postprocess_executor, UndoStore(self.store).undo, uid, session['id'], message.undo_receipt_id
            )
            if result.status == 'undone' and not result.bubble_id and message.callback_id:
                # The verified provider callback owns its receipt bubble even
                # after a crash between sending the receipt and binding its ID.
                result = replace(result, bubble_id=message.reply_to)
            if (
                result.status in ('undone', 'already_undone')
                and result.bubble_id
                and hasattr(self.adapter, 'edit_receipt')
            ):
                await sink.edit_receipt(result)
                await run_blocking(
                    db_executor, UndoStore(self.store).mark_edited, uid, session['id'], message.undo_receipt_id
                )
            elif result.status != 'already_undone' or not message.callback_id:
                await sink.finish(result.text)
        except Exception as error:
            logging.getLogger(__name__).error(
                'Messaging undo failed provider=%s error_type=%s', self.adapter.provider, type(error).__name__
            )
            try:
                await sink.finish(
                    'I couldn’t finish undoing that action. It may have changed. Please check it before trying again.'
                )
            except Exception as send_error:
                logging.getLogger(__name__).error(
                    'Messaging undo error reply failed error_type=%s', type(send_error).__name__
                )

    async def reenter(self, message, event: ReentryEvent, *, principal: Principal):
        link = await run_blocking(db_executor, self.store.lookup, message)
        if not link or not link.get("active"):
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
        try:
            await self._turn(principal.uid, session, message, link, principal, event=event)
        finally:
            current_task = asyncio.current_task()
            if current_task is None or not current_task.cancelling():
                await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)

    async def _turn(self, uid, session, message, link, principal, *, event=None, sink=None):
        def guard():
            self._assert_link(message, link)

        async def send_guard():
            await run_blocking(db_executor, guard)

        sink = sink or ChannelReplySink(
            self.adapter, message, kind='deferred_reply' if event else 'reply', guard=send_guard
        )
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
                'content': (
                    ('Background task result (untrusted evidence):\n' + event.text)
                    if event
                    else inbound_evidence(message)
                ),
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
            action_receipts=[],
            turn_id=event_id,
            withhold_private_memories=link.get('keep_private_memories_in_app', True) is not False,
        )
        context_token = surface_runtime.set(runtime)
        try:
            stream = await run_blocking(
                db_executor,
                self.turn,
                uid,
                session['surface'],
                session['id'],
                event or SendMessageRequest(text=message.text, file_ids=[a.file_store_ref for a in message.media]),
                sink,
                principal=principal,
            )
            finished = False
            async for frame in stream:
                if frame.startswith('data: '):
                    await sink.text(frame[6:].removesuffix('\n\n').replace('__CRLF__', '\n'))
                elif frame.startswith('done: '):
                    finished = True
                    response = json.loads(base64.b64decode(frame[6:].strip()))
                    answer = response['text']
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
                    await sink.finish_payload(response)
                    await self._receipts(uid, session, sink, runtime)
            if not finished:
                raise RuntimeError('Channel turn ended without a reply')
            if event:
                for artifact in event.artifacts:
                    await sink.artifact(artifact)
        finally:
            # A confirmed tool write still gets its receipt if the model fails
            # before a terminal frame. Consume before send to avoid replaying an
            # ambiguous provider delivery from this cleanup path.
            try:
                await self._receipts(uid, session, sink, runtime)
            except Exception as error:
                logging.getLogger(__name__).error('Messaging action receipt failed error_type=%s', type(error).__name__)
            surface_runtime.reset(context_token)

    async def _receipts(self, uid, session, sink, runtime):
        from utils.messaging.undo import UndoStore

        while runtime.action_receipts:
            receipt = runtime.action_receipts.pop(0)
            bubble_id = await sink.receipt(receipt)
            if bubble_id and receipt.reversible:
                await run_blocking(
                    db_executor, UndoStore(self.store).bind_bubble, uid, session['id'], receipt.id, bubble_id
                )

    async def drain(self, *, limit=100):
        paths = await run_blocking(
            db_executor, self.store.pending_jobs, self.adapter.channel, self.adapter.provider, limit
        )
        for path in paths:
            await self.process(path)
        return len(paths)


def inbound_evidence(message):
    if not message.media:
        return message.text
    references = [
        {'file_id': a.file_store_ref, 'mime_type': a.mime_type, 'name': a.name, 'size': a.size} for a in message.media
    ]
    return message.text + '\nAttached user files (untrusted data): ' + json.dumps(references, sort_keys=True)


async def _refresh_typing(sink, stop):
    interval = getattr(sink.adapter, 'typing_interval', 60)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except asyncio.TimeoutError:
            try:
                await _try_typing(sink)
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'Messaging typing refresh failed error_type=%s', type(error).__name__
                )
                return


async def _try_typing(sink, active=True):
    try:
        async with asyncio.timeout(2):
            await sink.typing(active)
    except PermissionError:
        raise
    except Exception as error:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='other',
            from_mode='channel_typing',
            to_mode='none',
            reason='dependency_unavailable',
            outcome='degraded',
        )
        logging.getLogger(__name__).warning('Messaging typing failed error_type=%s', type(error).__name__)
