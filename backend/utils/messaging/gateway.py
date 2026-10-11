"""Webhook admission and separately invoked durable workers; no provider branches."""

import asyncio
import base64
import logging
import json
import time
from contextlib import asynccontextmanager
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
from utils.messaging.undo import UndoStore
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
        try:
            return await self._process_claimed(path, payload)
        except BaseException as error:
            if not _worker_shutting_down() and isinstance(error, (Exception, asyncio.CancelledError)):
                # Retain the running row and its reconciliation evidence, but a
                # fully unwound failure must no longer block newer FIFO jobs.
                await run_blocking(db_executor, self.store.settle, path)
            raise
        finally:
            # A lease miss puts this head back to pending. Waking it here spins
            # the worker until the lease disappears. The holder, or the periodic
            # drain, admits it once the surface is free. A wake fault must not
            # replace the turn's own result.
            try:
                clock = payload.get('received_at')
                body = payload
                if isinstance(clock, str):
                    body = dict(payload, received_at=datetime.fromisoformat(clock))
                await self._wake_pending(ChannelMessage(**body), skip_path=path)
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'Messaging next-head wake failed provider=%s error_type=%s',
                    self.adapter.provider,
                    type(error).__name__,
                )

    async def _process_claimed(self, path, payload):
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

        async def guard():
            await run_blocking(db_executor, self._assert_link, message, link)

        sink = ChannelReplySink(self.adapter, message, guard=guard)
        session = token = None
        async with _typing(sink) as stop_typing:
            try:
                session = await run_blocking(db_executor, self.store.session, uid, message, link)
                token = await run_blocking(db_executor, self.store.acquire, uid, session['surface'])
                logging.getLogger(__name__).info(
                    'Messaging phase=lease provider=%s acquired=%s queue_age_ms=%.1f',
                    self.adapter.provider,
                    token is not None,
                    (datetime.now(timezone.utc) - message.received_at).total_seconds() * 1000,
                )
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
                        if not message.callback_id:
                            await sink.finish('Use Undo on the specific action confirmation.')
                    else:
                        # The inverse owns its durable receipt claim. It must not
                        # monopolize the chat lease while canonical privacy cleanup
                        # scans derived projections. Never replay a running inverse.
                        if not message.undo_receipt_id:
                            selected = await run_blocking(
                                db_executor, UndoStore(self.store).select_receipt, uid, session['id']
                            )
                            if not selected:
                                await sink.finish('There is no unambiguous reversible action in this chat.')
                            else:
                                message = replace(message, undo_receipt_id=selected)
                        if message.undo_receipt_id:
                            assert message.undo_receipt_id is not None
                            await run_blocking(
                                db_executor,
                                self.store.append_event,
                                uid,
                                session['id'],
                                {
                                    'id': 'undo:' + key(message.provider_message_id),
                                    'kind': 'undo_request',
                                    'at': message.received_at.isoformat(),
                                    'role': 'user',
                                    'content': 'Undo requested for receipt '
                                    + message.undo_receipt_id
                                    + '. Cleanup may be pending; verify state with tools before claiming it succeeded.',
                                },
                            )
                            start_background_task(
                                self._undo_action(uid, session, message, sink), name='messaging-undo-action'
                            )
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
                await stop_typing()
                if token is not None and session is not None:
                    await self._settle_failure(sink, uid, session['surface'], token)
                raise
            else:
                # Delivery succeeded. A tombstone-write fault must not tell the user
                # their accepted reply failed; leave the row for reconciliation.
                try:
                    await run_blocking(db_executor, self.store.complete, path)
                finally:
                    await run_blocking(db_executor, self.store.release, uid, session['surface'], token)
                    logging.getLogger(__name__).info(
                        'Messaging phase=lease_released provider=%s', self.adapter.provider
                    )
        return True

    async def _undo_action(self, uid, session, message, sink):
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
            elif not message.callback_id:
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
        fence_ids = {event.event_id, 'reply:' + event.event_id, 'failed:' + event.event_id}
        if any(e['id'] in fence_ids for e in events):
            # A started or failed reentry already ran tools or stored its fence.
            # Do not execute them again; the surface stays available.
            await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)
            await self._wake_pending(message)
            return

        async def send_guard():
            await run_blocking(db_executor, self._assert_link, message, link)

        sink = ChannelReplySink(self.adapter, message, kind='deferred_reply', guard=send_guard)
        try:
            async with _typing(sink):
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
            await self._wake_pending(message)
            raise
        else:
            await run_blocking(db_executor, self.store.release, principal.uid, session['surface'], token)
            await self._wake_pending(message)

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
                'at': message.received_at.isoformat(),
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
            request_at=message.received_at,
            withhold_private_memories=link.get('keep_private_memories_in_app', True) is not False,
        )
        context_token = surface_runtime.set(runtime)
        stream = None
        terminal = False
        turn_error = False
        reply_event = None
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
            await self._receipts(uid, session, sink, runtime)
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
            try:
                # Confirm completed writes even when the model fails to finish.
                await self._receipts(uid, session, sink, runtime)
            except Exception as error:
                logging.getLogger(__name__).error('Messaging action receipt failed error_type=%s', type(error).__name__)
            finally:
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

    async def _wake_pending(self, message, *, skip_path=None):
        if not self.wake or _worker_shutting_down():
            return
        pending = await run_blocking(db_executor, self.store.pending, message)
        if pending and pending[0] != skip_path:
            start_background_task(self.wake((pending[0],)), name='messaging-inbox-next')

    async def _receipts(self, uid, session, sink, runtime):
        while runtime.action_receipts:
            receipt = runtime.action_receipts.pop(0)
            bubble_id = await sink.receipt(receipt)
            await run_blocking(
                db_executor,
                self.store.append_event,
                uid,
                session['id'],
                {
                    'id': 'action:' + receipt.id,
                    'kind': 'action_receipt',
                    'at': datetime.now(timezone.utc).isoformat(),
                    'role': 'assistant',
                    'content': 'Confirmed action receipt: ' + receipt.text,
                },
            )
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


@asynccontextmanager
async def _typing(sink):
    stop = asyncio.Event()
    task = None
    stopped = False
    started = time.monotonic()

    async def stop_indicator():
        nonlocal stopped
        if stopped:
            return
        stopped = True
        stop.set()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            await _try_typing(sink, False)
        except asyncio.CancelledError:
            start_background_task(_try_typing(sink, False), name='messaging-typing-stop')

    try:
        await _try_typing(sink)
        logging.getLogger(__name__).info(
            'Messaging phase=typing provider=%s elapsed_ms=%.1f',
            sink.adapter.provider,
            (time.monotonic() - started) * 1000,
        )
        task = start_background_task(_refresh_typing(sink, stop), name='messaging-typing')
        yield stop_indicator
    finally:
        await stop_indicator()


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
        record_fallback(
            component='other',
            from_mode='channel_typing',
            to_mode='none',
            reason='dependency_unavailable',
            outcome='degraded',
        )
        logging.getLogger(__name__).warning('Messaging typing failed error_type=%s', type(error).__name__)
