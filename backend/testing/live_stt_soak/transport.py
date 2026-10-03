"""Local protocol peers and real-transport close injection, scoped to this app."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlsplit

import websockets
from websockets.legacy.server import serve


class ProviderConnections:
    def __init__(self, mode: str, fault_after: float, faults: int) -> None:
        self.mode = mode
        self.fault_after = fault_after
        self.remaining = faults
        self.tasks: set[asyncio.Task[Any]] = set()
        self.injected = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(websockets, name)

    async def connect(self, uri: str, **kwargs: Any) -> Any:
        host = urlsplit(uri).hostname
        family = (
            'soniox' if host == 'stt-rt.soniox.com' else 'modulate' if host == 'modulate-developer-apis.com' else None
        )
        if family is None:
            raise ValueError('soak permits only Soniox and Modulate WebSocket transports')
        fault = self.remaining > 0 and self.fault_after > 0
        if fault:
            self.remaining -= 1
        target = f'ws://127.0.0.1:9090/{family}?fault={int(fault)}' if self.mode == 'fake' else uri
        connection = await websockets.connect(target, **kwargs)
        if fault:

            async def close_transport() -> None:
                await asyncio.sleep(self.fault_after)
                if not connection.close_code:
                    self.injected += 1
                    await connection.close(code=1011, reason='isolated_soak_provider_fault')

            task = asyncio.create_task(close_transport(), name='soak-provider-close')
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        return connection

    async def shutdown(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def fake_provider(ws: Any, path: str) -> None:
    family = urlsplit(path).path.strip('/')
    fault = urlsplit(path).query == 'fault=1'
    samples = 0
    emitted = 0
    try:
        async for data in ws:
            if data == b'' or data == '':
                await ws.send(json.dumps({'finished': True} if family == 'soniox' else {'type': 'done'}))
                break
            if not isinstance(data, bytes):
                continue
            if data.startswith(b'RIFF'):
                data = data[44:]
            samples += len(data) // 2
            if samples - emitted < 16000 or fault:
                continue
            start, end = emitted / 16, samples / 16
            emitted = samples
            if family == 'soniox':
                msg = {
                    'tokens': [
                        {
                            'text': ' synthetic speech',
                            'start_ms': start,
                            'end_ms': end,
                            'is_final': True,
                            'speaker': '0',
                        },
                        {'text': '<end>', 'is_final': True},
                    ]
                }
            else:
                msg = {
                    'type': 'utterance',
                    'utterance': {
                        'text': 'Synthetic speech.',
                        'start_ms': start,
                        'duration_ms': end - start,
                        'speaker_id': 0,
                    },
                }
            await ws.send(json.dumps(msg))
    except websockets.exceptions.ConnectionClosed:
        pass


async def start_fake_server() -> Any:
    return await serve(fake_provider, '127.0.0.1', 9090)
