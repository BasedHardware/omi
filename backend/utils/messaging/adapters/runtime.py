"""Explicit opt-in construction and restart recovery, with no import-time IO."""

import asyncio
import logging
import os

from utils.executors import start_background_task

logger = logging.getLogger(__name__)


def configured_adapters():
    if os.getenv('OMI_MESSAGING_CHANNELS', 'off') != 'on':
        return ()
    from utils.messaging.adapters.telegram import TelegramAdapter
    from utils.messaging.adapters.linq import IMessageAdapter, LinqProvider
    from utils.messaging.adapters.transport import Transport

    adapters = []
    if os.getenv('OMI_TELEGRAM_ENABLED', 'off') == 'on':
        streaming = os.getenv('OMI_TELEGRAM_STREAMING', 'draft')
        if streaming not in ('draft', 'edit', 'none'):
            raise ValueError('Unsupported Telegram streaming mode')
        adapters.append(
            TelegramAdapter(
                os.environ['TELEGRAM_BOT_TOKEN'],
                os.environ['TELEGRAM_WEBHOOK_SECRET'],
                streaming=streaming,
            )
        )
    if os.getenv('OMI_IMESSAGE_ENABLED', 'off') == 'on':
        provider = os.getenv('OMI_IMESSAGE_PROVIDER', 'linq')
        if provider != 'linq':
            raise ValueError('iMessage provider is not installed')
        transport = Transport()
        client = LinqProvider(
            os.environ['LINQ_API_KEY'],
            os.environ['LINQ_WEBHOOK_SECRET'],
            transport=transport,
            sleep=asyncio.sleep,
            upload_hosts={'uploads.linqapp.com'},
        )
        adapters.append(
            IMessageAdapter(
                client,
                transport=transport,
                max_ratio=int(os.getenv('OMI_IMESSAGE_MAX_SEND_RECEIVE_RATIO', '3')),
                contact_card=os.getenv('OMI_IMESSAGE_CONTACT_CARD', 'off') == 'on',
            )
        )
    return tuple(adapters)


async def recover_pending(gateways, stop, *, interval=30):
    # Running jobs/leases are deliberately excluded: effects/delivery may be ambiguous.
    while not stop.is_set():
        for gateway in gateways:
            try:
                await gateway.drain(limit=100)
            except Exception as error:
                logger.warning(
                    'Messaging recovery paused provider=%s error_type=%s',
                    gateway.adapter.provider,
                    type(error).__name__,
                )
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except asyncio.TimeoutError:
            continue


def start_adapters(register):
    gateways = tuple(register(adapter.channel, adapter) for adapter in configured_adapters())
    if not gateways:
        return None
    stop = asyncio.Event()
    task = start_background_task(recover_pending(gateways, stop), name='messaging-pending-recovery')
    return stop, task
