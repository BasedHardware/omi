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


def _worker_shutting_down():
    task = asyncio.current_task()
    return task is not None and task.cancelling()


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
            # Task.cancel() means executor work may still be running. A
            # CancelledError raised inside a finished turn does not.
            if _worker_shutting_down():
                logging.getLogger(__name__).warning(
                    'Messaging job stopped provider=%s reason=worker_cancelled', self.adapter.provider
                )
                raise
            logging.getLogger(__name__).error(
                'Messaging job failed provider=%s reason=turn_cancelled error_type=CancelledError status_code=None',
                self.adapter.provider,
            )
            return False
        except Exception as error:
            # Settled failures are already fenced. Do not re-raise: the wake
            # batch must continue, and exception text can contain user content.
            logging.getLogger(__name__).error(
                'Messaging job failed provider=%s reason=%s error_type=%s status_code=%s',
                self.adapter.provider,
                getattr(error, 'reason', 'outbound_gate' if isinstance(error, PermissionError) else 'worker_error'),
                type(error).__name__,
                getattr(error, 'status_code', None),
            )
            return False

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
        except BaseException as error:
            # Keep the inbox row running: its effects still need reconciliation.
            # A task that is still cancelling may have executor work in flight,
            # so that lease stays until an operator proves the worker stopped.
            if _worker_shutting_down() or not isinstance(error, (Exception, asyncio.CancelledError)):
                raise
            await self._settle_failure(sink, uid, session['surface'], token)
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
        fence_ids = {event.event_id, 'reply:' + event.event_id, 'failed:' + event.event_id}
        if any(e['id'] in fence_ids for e in events):
            # A started or failed reentry already ran tools or stored its fence.
            # Do not execute them again; the surface stays available.
            await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)
            return

        async def send_guard():
            await run_blocking(db_executor, self._assert_link, message, link)

        sink = ChannelReplySink(self.adapter, message, kind='deferred_reply', guard=send_guard)
        try:
            await self._turn(principal.uid, session, message, link, principal, event=event, reply_sink=sink)
        except BaseException as error:
            if _worker_shutting_down() or not isinstance(error, (Exception, asyncio.CancelledError)):
                raise
            await self._settle_failure(
                sink,
                principal.uid,
                session['surface'],
                token,
                fence=(
                    None
                    if sink.finished
                    else (
                        principal.uid,
                        session['id'],
                        {
                            'id': 'failed:' + event.event_id,
                            'kind': 'message',
                            'at': datetime.now(timezone.utc).isoformat(),
                            'role': 'assistant',
                            'content': 'Sorry, I could not finish that reply. Please try again.',
                        },
                    )
                ),
            )
            raise
        else:
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
            # Cancellation injects CancelledError at the next await; catch it so
            # the indicator still stops and the context token is always reset.
            if stream is not None and hasattr(stream, 'aclose'):
                try:
                    await stream.aclose()
                except asyncio.CancelledError:
                    pass
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
            try:
                await _stop_typing(sink)
            except asyncio.CancelledError:
                start_background_task(_stop_typing(sink), name='messaging-typing-stop')
            surface_runtime.reset(context_token)

    async def _settle_failure(self, sink, uid, surface, token, *, fence=None):
        # One notice, and only when the reply itself was not accepted.
        delivered = sink is not None and sink.finished
        try:
            if sink is not None and not delivered:
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
            if sink is not None and not delivered:
                record_fallback(
                    component='other',
                    from_mode='channel_turn',
                    to_mode='failure_notice',
                    reason='other',
                    outcome='degraded',
                )
        finally:
            if fence is not None and not delivered:
                try:
                    await run_blocking(db_executor, self.store.append_event, fence[0], fence[1], fence[2])
                except Exception as error:
                    logging.getLogger(__name__).warning(
                        'Messaging failure fence failed provider=%s error_type=%s',
                        self.adapter.provider,
                        type(error).__name__,
                    )
            await run_blocking(db_executor, self.store.release, uid, surface, token)

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


async def _stop_typing(sink):
    try:
        await sink.typing(False)
    except Exception as error:
        logging.getLogger(__name__).warning('Messaging typing stop failed error_type=%s', type(error).__name__)


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
