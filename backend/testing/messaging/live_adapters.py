#!/usr/bin/env python3
"""Interactive real-provider/real-turn dev harness. Never invoked by CI.

The configured dev webhook must tunnel to this loopback listener. A human uses
separate Telegram/iMessage test clients; Bot API cannot impersonate an inbound
user. Runtime Secret Manager reads use the documented human payload tier.
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

REQUIRED = (
    'test_uid',
    'test_account_verified',
    'telegram_test_user_id',
    'linq_test_handle',
    'telegram_dev_bot_id',
    'linq_dev_line',
    'webhook_origin',
    'secret_project',
)
SECRET_NAMES = ('telegram-bot-token-dev', 'telegram-webhook-secret-dev', 'linq-api-key-dev', 'linq-webhook-secret-dev')
CASES = (
    'link',
    'help',
    'text',
    'long_reply',
    'citations',
    'voice',
    'photo',
    'document',
    'send_file',
    'reaction',
    'task_write',
    'undo',
    'unlink',
)


def validate_config(config):
    missing = [field for field in REQUIRED if not config.get(field)]
    if missing:
        raise ValueError('Missing setup fields: ' + ', '.join(missing))
    if config['test_account_verified'] is not True or config['secret_project'] != 'based-hardware-dev':
        raise ValueError('Dedicated Omi test account and dev secret project required')
    parsed = urlparse(config['webhook_origin'])
    if parsed.scheme != 'https' or parsed.hostname == 'api.omi.me' or parsed.query or parsed.path not in ('', '/'):
        raise ValueError('Dedicated HTTPS dev webhook origin required')
    return config


def read_secrets(config):
    # gcp-agent-env.sh declares payload reads human-only. Never silently fall
    # back to David's interactive ADC from a read-only agent tier.
    if os.getenv('GCP_AGENT_TIER') != 'human':
        raise PermissionError('Secret payload reads require the documented human tier')
    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    values = {}
    for name in SECRET_NAMES:
        resource = f"projects/{config['secret_project']}/secrets/{name}/versions/latest"
        values[name] = client.access_secret_version(request={'name': resource}).payload.data.decode()
    return values


class Transcript:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids mixing runs. Dedicated synthetic test content only.
        self.file = self.path.open('x', encoding='utf-8')
        os.chmod(self.path, 0o600)

    def append(self, **event):
        self.file.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), **event}) + '\n')
        self.file.flush()


def build_app(config, secrets, transcript):
    from fastapi import FastAPI, Request, HTTPException
    from utils.messaging.adapters.telegram import TelegramAdapter
    from utils.messaging.adapters.linq import LinqProvider, IMessageAdapter
    from utils.messaging.adapters.transport import Transport
    from utils.messaging.gateway import Gateway
    from utils.messaging.access import require_access
    from utils.executors import start_background_task
    from utils.messaging.adapters.runtime import recover_pending

    transport = Transport()
    telegram = TelegramAdapter(
        secrets['telegram-bot-token-dev'], secrets['telegram-webhook-secret-dev'], transport=transport
    )
    linq = LinqProvider(
        secrets['linq-api-key-dev'],
        secrets['linq-webhook-secret-dev'],
        transport=transport,
        sleep=asyncio.sleep,
        upload_hosts={'uploads.linqapp.com'},
    )
    imessage = IMessageAdapter(linq, transport=transport)
    gateways = {}
    from database.messaging import MessagingStore
    from google.cloud.firestore_v1 import FieldFilter
    from utils.messaging.identity import key

    class TestAccountStore(MessagingStore):
        def __init__(self, adapter, external_id):
            super().__init__()
            self.adapter, self.external_id = adapter, external_id

        def user(self, uid):
            if uid != config['test_uid']:
                raise PermissionError('Non-test account storage forbidden')
            return super().user(uid)

        def identity(self, channel, provider, external_id):
            if (channel, provider, external_id) != (self.adapter.channel, self.adapter.provider, self.external_id):
                raise PermissionError('Non-test channel storage forbidden')
            return super().identity(channel, provider, external_id)

        def pending_jobs(self, channel, provider, limit=100):
            identity = self.identity(channel, provider, self.external_id)
            return [
                doc.reference.path
                for doc in identity.collection('inbox')
                .where(filter=FieldFilter('status', '==', 'pending'))
                .limit(limit)
                .stream()
            ]

        def claim(self, path):
            prefix = self.identity(self.adapter.channel, self.adapter.provider, self.external_id).path + '/inbox/'
            if not path.startswith(prefix):
                raise PermissionError('Non-test inbox forbidden')
            return super().claim(path)

    def admit(uid):
        if uid != config['test_uid']:
            raise PermissionError('Harness accepts only the verified Omi test account')
        require_access(uid)

    for adapter, external_id in (
        (telegram, str(config['telegram_test_user_id'])),
        (imessage, config['linq_test_handle']),
    ):
        # Install instance closures, keeping the actual adapter methods unchanged.
        parse, send = adapter.parse, adapter.send
        channel = adapter.channel

        def restricted_parse(body, parse=parse, external_id=external_id, channel=channel):
            messages = parse(body)
            if channel == 'imessage' and messages:
                data = json.loads(body)['data']
                owner = data.get('chat', {}).get('owner_handle', {}).get('handle') or data.get(
                    'recipient_handle', {}
                ).get('handle')
                if owner != config['linq_dev_line']:
                    raise PermissionError('Linq DEV line mismatch')
            if any(message.external_user_id != external_id for message in messages):
                raise PermissionError('Non-test sender rejected before persistence')
            for message in messages:
                text = '[link proof redacted]' if message.link_proof else message.text
                transcript.append(
                    layer='live-dev',
                    channel=channel,
                    direction='inbound',
                    text=text,
                    attachments=len(message.attachments),
                    message_hash=hashlib.sha256(message.provider_message_id.encode()).hexdigest(),
                )
            return messages

        async def observed_send(message, *, text=None, artifact=None, draft=False, send=send, channel=channel):
            await send(message, text=text, artifact=artifact, draft=draft)
            if not draft:
                transcript.append(
                    layer='live-dev',
                    channel=channel,
                    direction='outbound',
                    text=text,
                    artifact=artifact.name if artifact else None,
                    state='provider-accepted',
                )

        adapter.parse = restricted_parse
        adapter.send = observed_send
        gateway = Gateway(adapter, store=TestAccountStore(adapter, external_id), admission=admit)

        async def wake(paths, gateway=gateway):
            for path in paths:
                try:
                    await gateway.process(path)
                except Exception as error:
                    transcript.append(
                        layer='live-dev',
                        channel=gateway.adapter.channel,
                        state='blocked',
                        error_type=type(error).__name__,
                    )

        gateway.wake = wake
        gateways[channel] = gateway

    app = FastAPI()

    @app.post('/v1/messaging/webhooks/{channel}', status_code=202)
    async def webhook(channel: str, request: Request):
        gateway = gateways.get(channel)
        if gateway is None:
            raise HTTPException(status_code=404)
        body = await request.body()
        if len(body) > 1_000_000:
            raise HTTPException(status_code=413)
        try:
            await gateway.webhook(body, request.headers)
        except PermissionError:
            raise HTTPException(status_code=401, detail='Webhook rejected') from None
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid webhook') from None
        return {'status': 'accepted'}

    @app.on_event('startup')
    async def startup():
        # Verify bot identity before accepting any inbound traffic or sending.
        result = await telegram.api('getMe', {}, idempotent=True)
        if str(result['result']['id']) != str(config['telegram_dev_bot_id']):
            raise PermissionError('Telegram DEV bot identity mismatch')
        info = await telegram.api('getWebhookInfo', {}, idempotent=True)
        expected = config['webhook_origin'].rstrip('/') + '/v1/messaging/webhooks/telegram'
        if info['result'].get('url') != expected:
            raise PermissionError('Telegram dev webhook not configured for this harness')
        numbers = await linq.api('GET', '/phone_numbers', idempotent=True)
        if config['linq_dev_line'] not in {row['phone_number'] for row in numbers.get('phone_numbers', ())}:
            raise PermissionError('Linq DEV sandbox line unavailable')
        transcript.append(layer='live-dev', state='ready', cases=list(CASES))
        app.state.stop = asyncio.Event()
        app.state.recovery = start_background_task(
            recover_pending(tuple(gateways.values()), app.state.stop), name='live-messaging-recovery'
        )

    @app.on_event('shutdown')
    async def shutdown():
        app.state.stop.set()
        app.state.recovery.cancel()
        try:
            await app.state.recovery
        except asyncio.CancelledError:
            pass
        transcript.append(layer='live-dev', state='stopped')
        transcript.file.close()

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Non-secret dev setup JSON; see adapter runbook')
    parser.add_argument('--transcript', required=True, help='New local JSONL path, never committed')
    parser.add_argument(
        '--check-only', action='store_true', help='Validate non-secret config without secrets or cloud IO'
    )
    parser.add_argument('--port', type=int, default=8088)
    args = parser.parse_args()
    config = validate_config(json.loads(Path(args.config).read_text()))
    if args.check_only:
        print('Non-secret setup configuration valid. Live providers NOT RUN.')
        return
    # Must load the backend's documented dev environment before importing clients.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ['OMI_ENV_STAGE'] = 'dev'
    from utils.env_loader import load_backend_env

    load_backend_env()
    os.environ['OMI_MESSAGING_CHANNELS'] = 'on'
    os.environ['OMI_MESSAGING_CHANNELS_UIDS'] = config['test_uid']
    secrets = read_secrets(config)
    transcript = Transcript(args.transcript)
    app = build_app(config, secrets, transcript)
    import uvicorn

    print('Use only separate QA clients and synthetic content. Link in Omi, then exercise the runbook cases.')
    uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False, log_level='warning')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # No exception repr or traceback: SDK exceptions may embed secrets/URLs.
        print('Live harness blocked: ' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
