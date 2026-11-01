"""Incremental album media preparation before the inbox generation fence.

Keep media/decoder imports on the channel worker path; storage admission imports
only the pure album merge rules, including on services without channel adapters.
"""

from datetime import datetime
from dataclasses import replace

from utils.executors import db_executor, run_blocking
from utils.messaging.contracts import Artifact, ChannelMessage, InboundAttachment
from utils.messaging.adapters.media import MediaPreparationError
from utils.messaging.metrics import FAILURES
from utils.observability.fallback import record_fallback

VOICE_DISABLED_REPLY = 'Voice notes are turned off for this chat. Send a text message instead.'


def inbox_message(payload):
    payload = dict(payload)
    payload['received_at'] = datetime.fromisoformat(payload['received_at'])
    payload['media'] = tuple(Artifact(**a) for a in payload.get('media', ()))
    payload['attachments'] = tuple(InboundAttachment(**a) for a in payload.get('attachments', ()))
    return ChannelMessage(**payload)


async def prepare_for_generation(adapter, store, path, message, uid, session, guard, *, allow_voice=True):
    if not message.media_group_id:
        if not allow_voice:
            message = replace(message, attachments=tuple(a for a in message.attachments if not a.voice))
            if not message.text.strip() and not message.attachments and not message.media:
                raise MediaPreparationError('voice_disabled', VOICE_DISABLED_REPLY)
        return await adapter.prepare(message, uid, session, guard) if hasattr(adapter, 'prepare') else message
    raw = message
    prepared = None
    failures = []
    succeeded = False
    while True:
        # Only new references are downloaded/ingested when admission races media IO.
        batch = (
            raw
            if prepared is None
            else replace(
                raw,
                attachments=raw.attachments[len(message.attachments) :],
                media=prepared.media,
                text=prepared.text + raw.text[len(message.text) :],
            )
        )
        if not allow_voice:
            # Keep the full raw count for CAS, but never reintroduce disabled audio
            # when a late arrival causes another snapshot read.
            batch = replace(batch, attachments=tuple(a for a in batch.attachments if not a.voice))
        try:
            prepared = (
                await adapter.prepare(batch, uid, session, guard)
                if (hasattr(adapter, 'prepare') and (batch.attachments or batch.media or batch.text.strip()))
                else batch
            )
            succeeded = succeeded or bool(batch.attachments or batch.media)
        except MediaPreparationError as error:
            failures.append(error)
            prepared = replace(
                batch,
                attachments=(),
                text=batch.text + '\nAttachment preparation notice (untrusted context): ' + error.reply,
            )
        latest = await run_blocking(db_executor, store.seal_album, path, len(raw.attachments))
        if latest is None:
            if failures and not succeeded:
                raise failures[0]
            if not allow_voice and not prepared.media and not prepared.text.strip():
                raise MediaPreparationError('voice_disabled', VOICE_DISABLED_REPLY)
            if failures:
                for error in failures:
                    FAILURES.labels(message.channel, error.reason).inc()
                record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
            return prepared
        message, raw = raw, inbox_message(latest)
