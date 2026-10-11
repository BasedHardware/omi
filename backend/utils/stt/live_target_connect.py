"""Connect a registry endpoint through the existing Modulate socket protocol."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlencode

import websockets

from utils.stt.live_router import connecting_target
from utils.stt import streaming


async def connect_modulate(callback, sample_rate, language):
    target = connecting_target.get()
    if target is None or target.endpoint is None:
        socket = await streaming.process_audio_modulate(callback, sample_rate, language)
        setattr(socket, 'routing_endpoint', None)
        return socket
    key = os.getenv('MODULATE_API_KEY')
    if not key:
        raise ValueError('Modulate credential missing')
    params = {
        'api_key': key,
        'speaker_diarization': 'true',
        'partial_results': 'true',
        'sample_rate': str(sample_rate),
        'audio_format': 's16le',
        'num_channels': '1',
    }
    if language and language != 'multi':
        params['language'] = language
    ws = await websockets.connect(target.endpoint + '?' + urlencode(params), ping_timeout=10, ping_interval=10)
    socket = streaming.SafeModulateSocket(ws, callback, asyncio.get_running_loop())
    setattr(socket, 'routing_endpoint', target.endpoint)
    return socket
