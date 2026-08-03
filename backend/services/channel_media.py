import base64
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import httpx

from utils.executors import storage_executor, run_blocking
from utils.http_client import get_webhook_client, safe_request_target
from utils.llm.openglass import describe_image

CHANNEL_MEDIA_MAX_BYTES = 20 * 1024 * 1024
CHANNEL_MEDIA_MAX_ATTACHMENTS = 10
CHANNEL_MEDIA_MAX_TEXT_BYTES = 64 * 1024
CHANNEL_MEDIA_MAX_VISION_BYTES = 10 * 1024 * 1024


class ChannelMediaError(RuntimeError):
    pass


def _setting(name: str) -> Optional[str]:
    value = os.getenv(name, '').strip()
    return value or None


def _allowed_host(source: str, hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip('.')
    if source == 'telegram':
        return host == 'api.telegram.org'
    if source == 'twilio':
        return host == 'api.twilio.com' or host.endswith('.twilio.com')
    if source == 'imessage':
        return host == 'api.sendblue.com' or host.endswith('.sendblue.com') or host.endswith('.sendblue.co')
    return False


def _validated_url(source: str, url: str) -> Tuple[str, Dict[str, Any]]:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not _allowed_host(source, parsed.hostname):
        raise ChannelMediaError('media URL is not an approved provider URL')
    try:
        return safe_request_target(url)
    except Exception as exc:
        raise ChannelMediaError('media URL could not be resolved safely') from exc


def _content_type(value: Optional[str], filename: str) -> str:
    raw = (value or '').split(';', 1)[0].strip().lower()
    if raw and raw != 'application/octet-stream':
        return raw
    return mimetypes.guess_type(filename)[0] or raw or 'application/octet-stream'


def _filename(value: Any, mime_type: str) -> str:
    candidate = Path(str(value or '')).name.strip()
    if candidate and candidate not in {'.', '..'}:
        return candidate[:180]
    return f'attachment{mimetypes.guess_extension(mime_type) or ""}'


async def _download_url(
    source: str,
    url: str,
    *,
    filename: str = '',
    headers: Optional[Dict[str, str]] = None,
    auth: Optional[httpx.BasicAuth] = None,
) -> Tuple[bytes, str, str]:
    request_url, request_options = _validated_url(source, url)
    client = get_webhook_client()
    request_headers = dict(headers or {})
    request_headers.update(request_options.get('headers', {}))
    async with client.stream(
        'GET',
        request_url,
        headers=request_headers,
        extensions=request_options.get('extensions'),
        auth=auth,
    ) as response:
        if response.status_code < 200 or response.status_code >= 300:
            raise ChannelMediaError('media provider returned an unsuccessful response')
        content_length = response.headers.get('content-length')
        if content_length and content_length.isdigit() and int(content_length) > CHANNEL_MEDIA_MAX_BYTES:
            raise ChannelMediaError('media attachment is too large')
        chunks = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > CHANNEL_MEDIA_MAX_BYTES:
                raise ChannelMediaError('media attachment is too large')
            chunks.append(chunk)
        mime_type = _content_type(response.headers.get('content-type'), filename)
        return b''.join(chunks), mime_type, _filename(filename, mime_type)


async def _telegram_download(file_id: str, filename: str, mime_type: str) -> Tuple[bytes, str, str]:
    token = _setting('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ChannelMediaError('Telegram credentials are not configured')
    api_url = f'https://api.telegram.org/bot{token}/getFile'
    request_url, request_options = _validated_url('telegram', api_url)
    client = get_webhook_client()
    response = await client.get(
        request_url,
        headers=request_options.get('headers'),
        extensions=request_options.get('extensions'),
        params={'file_id': file_id},
    )
    if response.status_code < 200 or response.status_code >= 300:
        raise ChannelMediaError('Telegram file lookup failed')
    body = response.json()
    file_path = body.get('result', {}).get('file_path') if isinstance(body, dict) else None
    if not isinstance(file_path, str) or not file_path:
        raise ChannelMediaError('Telegram file lookup returned no path')
    file_url = f'https://api.telegram.org/file/bot{token}/{file_path}'
    return await _download_url('telegram', file_url, filename=filename, headers=request_options.get('headers'))


async def _download_attachment(attachment: Dict[str, Any]) -> Tuple[bytes, str, str]:
    source = str(attachment.get('source') or '')
    filename = str(attachment.get('filename') or '')
    mime_type = str(attachment.get('mime_type') or '')
    file_id = attachment.get('file_id')
    if source == 'telegram' and isinstance(file_id, str) and file_id:
        return await _telegram_download(file_id, filename, mime_type)
    url = attachment.get('url')
    if not isinstance(url, str) or not url:
        raise ChannelMediaError('media attachment has no provider URL')
    auth = None
    if source == 'twilio':
        account_sid = _setting('TWILIO_ACCOUNT_SID')
        auth_token = _setting('TWILIO_AUTH_TOKEN')
        if account_sid and auth_token:
            auth = httpx.BasicAuth(account_sid, auth_token)
    return await _download_url(source, url, filename=filename, auth=auth)


def _describe_audio(path: str, uid: str) -> str:
    from utils.chat import transcribe_voice_message_segment

    transcript, _ = transcribe_voice_message_segment(path, uid)
    return transcript or ''


async def build_media_context(uid: str, attachments: Iterable[Dict[str, Any]]) -> str:
    contexts = []
    for attachment in list(attachments)[:CHANNEL_MEDIA_MAX_ATTACHMENTS]:
        filename = _filename(attachment.get('filename'), str(attachment.get('mime_type') or ''))
        try:
            data, mime_type, filename = await _download_attachment(attachment)
            if mime_type.startswith('image/') and len(data) <= CHANNEL_MEDIA_MAX_VISION_BYTES:
                description = await describe_image(uid, base64.b64encode(data).decode('ascii'), mime_type)
                contexts.append(
                    f'[Image attachment: {filename} ({mime_type})]\n{description or "No visual description was available."}'
                )
                continue
            if mime_type.startswith('audio/'):
                suffix = Path(filename).suffix or mimetypes.guess_extension(mime_type) or '.bin'
                temp_path = ''
                try:
                    with tempfile.NamedTemporaryFile(prefix='omi-channel-', suffix=suffix, delete=False) as temp_file:
                        temp_file.write(data)
                        temp_path = temp_file.name
                    transcript = await run_blocking(storage_executor, _describe_audio, temp_path, uid)
                finally:
                    if temp_path:
                        Path(temp_path).unlink(missing_ok=True)
                contexts.append(
                    f'[Audio attachment: {filename} ({mime_type})]\n{transcript or "No transcript was available."}'
                )
                continue
            if mime_type.startswith('text/') and len(data) <= CHANNEL_MEDIA_MAX_TEXT_BYTES:
                text = data.decode('utf-8', errors='replace').strip()
                contexts.append(f'[Text attachment: {filename} ({mime_type})]\n{text[:12000]}')
                continue
            contexts.append(f'[Media attachment: {filename} ({mime_type})]')
        except Exception:
            contexts.append(f'[Media attachment: {filename}; processing was unavailable]')
    return '\n\n'.join(contexts)
