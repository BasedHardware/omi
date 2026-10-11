"""Webhook admission and separately invoked durable workers; no provider branches."""

import asyncio
import base64
import logging
import json
from dataclasses import replace
from datetime import datetime, timezone

from database.messaging import MessagingStore
from utils.messaging.identity import key
from models.chat import SendMessageRequest
from utils.chat_turn import run_chat_turn
from utils.executors import db_executor, run_blocking, start_background_task
from utils.messaging.access import require_access
from utils.messaging.contracts import Artifact, ChannelMessage, InboundAttachment, Principal, ReentryEvent
from utils.messaging.history import append_digest, history_tool
from utils.messaging.outbound import ChannelReplySink
from utils.messaging.projection import SurfaceRuntime, surface_runtime
from utils.observability.fallback import record_fallback


class ChannelTurnError(RuntimeError):
    def __init__(self, reason):
        super().__init__('Channel turn failed')
        self.reason = reason


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
        if not messages:
            logging.getLogger(__name__).info(
                'Messaging ignored provider=%s reason=non_turn_event', self.adapter.provider
            )
        paths = []
        for message in messages:
            if (message.channel, message.provider) != (self.adapter.channel, self.adapter.provider):
                raise PermissionError('Adapter identity mismatch')
            path = await run_blocking(db_executor, self.store.enqueue, message)
            if path:
                paths.append(path)
            else:
                logging.getLogger(__name__).info(
                    'Messaging ignored provider=%s reason=duplicate_message', self.adapter.provider
                )
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
        try:
            return await self._process(path)
        except asyncio.CancelledError:
            logging.getLogger(__name__).warning(
                'Messaging job stopped provider=%s reason=worker_cancelled', self.adapter.provider
            )
            raise
        except Exception as error:
            logging.getLogger(__name__).error(
                'Messaging job failed provider=%s reason=%s error_type=%s status_code=%s',
                self.adapter.provider,
                getattr(error, 'reason', 'outbound_gate' if isinstance(error, PermissionError) else 'worker_error'),
                type(error).__name__,
                getattr(error, 'status_code', None),
            )
            raise

    async def _process(self, path):
        payload = await run_blocking(db_executor, self.store.claim, path)
        if payload is None:
            return False
        payload['received_at'] = datetime.fromisoformat(payload['received_at'])
        payload['media'] = tuple(Artifact(**a) for a in payload['media'])
        payload['attachments'] = tuple(InboundAttachment(**a) for a in payload.get('attachments', ()))
        message = ChannelMessage(**payload)
        if hasattr(self.adapter, 'admitted'):
            await self.adapter.admitted(message)
        link = await run_blocking(db_executor, self.store.lookup, message)
        if message.link_proof:
            try:
                owner = await run_blocking(db_executor, self.store.proof_owner, message.link_proof)
                await run_blocking(db_executor, self.admission, owner)
                link = await run_blocking(db_executor, self.store.consume, message.link_proof, message)
            except PermissionError:
                logging.getLogger(__name__).info(
                    'Messaging reply provider=%s reason=invalid_link_proof', self.adapter.provider
                )
                # Same fixed reply as an unknown sender. Do not distinguish a bad,
                # expired, or unauthorized proof.
                await ChannelReplySink(self.adapter, message).finish('Link your account in Omi to chat here.')
                await run_blocking(db_executor, self.store.complete, path)
                return True
        if not link or not link.get('active'):
            logging.getLogger(__name__).info(
                'Messaging reply provider=%s reason=unlinked_sender', self.adapter.provider
            )
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
            logging.getLogger(__name__).info(
                'Messaging deferred provider=%s reason=surface_busy', self.adapter.provider
            )
            await run_blocking(db_executor, self.store.retry, path)
            return False

        async def guard():
            await run_blocking(db_executor, self._assert_link, message, link)

        sink = ChannelReplySink(self.adapter, message, guard=guard)
        try:
            if message.command == 'help':
                await sink.finish(
                    'Chat with your Omi agent about your memories, tasks and files. '
                    'Reply undo within 5 minutes to reverse the last supported write. '
                    'Use /unlink to disconnect. Messages are used only to serve your chat.'
                )
            elif message.command == 'undo':
                from utils.messaging.undo import UndoStore

                await sink.finish(await run_blocking(db_executor, UndoStore(self.store).undo, uid, session['id']))
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
                    await self._turn(uid, session, message, link, Principal(uid), reply_sink=sink)
        except Exception:
            # The stopped worker must not block later messages. Keep this inbox
            # row running: its effects/receipts still require reconciliation.
            notice_needed = not sink.finished
            try:
                if notice_needed:
                    await sink.finish('Sorry, I could not finish that reply. Please try again.')
            except Exception as error:
                record_fallback(
                    component='other',
                    from_mode='channel_turn',
                    to_mode='failure_notice',
                    reason='other',
                    outcome='exhausted',
                )
                logging.getLogger(__name__).warning(
                    'Messaging failure reply failed provider=%s reason=delivery_failed error_type=%s status_code=%s',
                    self.adapter.provider,
                    type(error).__name__,
                    getattr(error, 'status_code', None),
                )
            else:
                if notice_needed:
                    record_fallback(
                        component='other',
                        from_mode='channel_turn',
                        to_mode='failure_notice',
                        reason='other',
                        outcome='degraded',
                    )
            finally:
                await run_blocking(db_executor, self.store.release, uid, session['surface'], token)
            raise
        except BaseException:
            # Cancellation can abandon executor work that is still running.
            # Keep its lease fenced until the operator proves that work stopped.
            raise
        else:
            # Delivery succeeded. A tombstone-write fault must not tell the user
            # their accepted reply failed; leave the row for reconciliation.
            try:
                await run_blocking(db_executor, self.store.complete, path)
            finally:
                await run_blocking(db_executor, self.store.release, uid, session['surface'], token)
        return True

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
        # Deferred results have no claimed inbox row fencing their replay.
        # Keep the lease on failure until effects/delivery are reconciled.
        await self._turn(principal.uid, session, message, link, principal, event=event)
        await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)

    async def _turn(self, uid, session, message, link, principal, *, event=None, reply_sink=None):
        def guard():
            self._assert_link(message, link)

        async def send_guard():
            await run_blocking(db_executor, guard)

        sink = reply_sink or ChannelReplySink(
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
            write_reports=[],
            withhold_private_memories=link.get('keep_private_memories_in_app', True) is not False,
        )
        context_token = surface_runtime.set(runtime)
        typing_stop = asyncio.Event()
        typing_task = start_background_task(_refresh_typing(sink, typing_stop), name='messaging-typing')
        stream = None
        terminal = False
        turn_error = False
        reply_event = None
        try:
            await sink.typing()
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
            async for frame in stream:
                if frame.startswith('data: '):
                    await sink.text(frame[6:].removesuffix('\n\n').replace('__CRLF__', '\n'))
                elif frame.startswith('done: '):
                    terminal = True
                    response = json.loads(base64.b64decode(frame[6:].strip()))
                    answer = response['text']
                    if not answer.strip():
                        raise ChannelTurnError('empty_reply')
                    reply_event = {
                        'id': 'reply:' + event_id,
                        'kind': 'message',
                        'at': datetime.now(timezone.utc).isoformat(),
                        'role': 'assistant',
                        'content': answer,
                    }
                    if runtime.write_reports:
                        response['text'] += '\n\n' + '\n'.join(runtime.write_reports)
                    await sink.finish_payload(response)
                elif frame.startswith('error: '):
                    # The shared producer can follow this with a persisted
                    # typed fallback. Drain it, including its quota cleanup.
                    turn_error = True
                    logging.getLogger(__name__).warning(
                        'Messaging turn issue provider=%s reason=turn_error_frame', self.adapter.provider
                    )
            if not terminal or reply_event is None:
                raise ChannelTurnError('turn_error_frame' if turn_error else 'missing_terminal_reply')
            if event:
                for artifact in event.artifacts:
                    await sink.artifact(artifact)
            # Generated text is not delivery evidence. Only accepted replies
            # enter subsequent model history or suppress deferred reentry.
            await run_blocking(db_executor, self.store.append_event, uid, session['id'], reply_event)
        finally:
            # Final delivery can raise while the generator is suspended at its
            # terminal yield. Close in this task's context, before resetting it.
            if stream is not None and hasattr(stream, 'aclose'):
                try:
                    await stream.aclose()
                except Exception as error:
                    logging.getLogger(__name__).warning(
                        'Messaging stream close failed provider=%s error_type=%s',
                        self.adapter.provider,
                        type(error).__name__,
                    )
            typing_stop.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass
            # A failed typing stop must not mask the original turn/delivery error.
            try:
                await sink.typing(False)
            except Exception as error:
                logging.getLogger(__name__).warning('Messaging typing stop failed error_type=%s', type(error).__name__)
            surface_runtime.reset(context_token)

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
                await sink.typing()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'Messaging typing refresh failed error_type=%s', type(error).__name__
                )
                return
