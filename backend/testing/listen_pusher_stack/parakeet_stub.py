"""Protocol-faithful local replacement for the Parakeet streaming endpoint.

The listen service still opens and drives its real ``ParakeetWebSocketSocket``.
This server only replaces the GPU/provider boundary and never inspects or
stores received PCM.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
app = FastAPI()


def _record(event: dict[str, Any]) -> None:
    """Write sanitized transport evidence when the harness asks for it."""
    state_dir = os.getenv('OMI_STACK_STATE_DIR')
    if not state_dir:
        return
    path = Path(state_dir) / 'parakeet.jsonl'
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True) + '\n')


@app.websocket('/v3/stream')
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    _record({'event': 'connected', 'sample_rate': websocket.query_params.get('sample_rate')})
    sent_segment = False
    try:
        while True:
            message = await websocket.receive()
            if message.get('type') == 'websocket.disconnect':
                return
            data = message.get('bytes')
            if data:
                _record({'event': 'pcm_received', 'bytes': len(data)})
                if not sent_segment:
                    # This is the smallest shape consumed by the production
                    # Parakeet WebSocket client and transcript processor.
                    await websocket.send_json(
                        {
                            'id': 'stack-segment-1',
                            'speaker': 'SPEAKER_00',
                            'start': 0.0,
                            'end': 0.1,
                            'text': 'stack transcript',
                            'is_user': False,
                            'person_id': None,
                        }
                    )
                    _record({'event': 'segment_sent'})
                    sent_segment = True
            elif message.get('text') == 'finalize':
                _record({'event': 'finalize_received'})
                return
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception('listen stack Parakeet stub failed')
        raise
