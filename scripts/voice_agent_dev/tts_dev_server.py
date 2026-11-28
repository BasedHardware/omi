"""Minimal local-dev server: TTS (Deepgram Aura -> ulaw_8000 for DevKit speaker)
+ /v4/listen relay (Deepgram STT streaming). Accepts ADMIN_KEY-prefixed tokens.
No Firebase/Firestore/Redis - for local dev loop only.
"""
import os, logging, asyncio, json
from typing import Any
from urllib.parse import urlencode, parse_qs

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('dev-server')

app = FastAPI()
DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"
DEEPGRAM_LISTEN_URL = "wss://api.deepgram.com/v1/listen"
DG_DEFAULT_MODEL = "aura-2-thalia-en"
ADMIN_KEY = os.getenv('ADMIN_KEY', 'local-dev-admin-key-')
DG_KEY = os.getenv('DEEPGRAM_API_KEY', '')

class Req(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice_id: str = ''
    model_id: str = ''
    output_format: str = 'mp3_44100_128'
    voice_settings: Any = None

def _check_token(token: str | None) -> str:
    if not token:
        return ''
    t = token.strip()
    if t.lower().startswith('bearer '):
        t = t.split(' ', 1)[1]
    if ADMIN_KEY and t.startswith(ADMIN_KEY):
        return t[len(ADMIN_KEY):] or 'devuser'
    if os.getenv('LOCAL_DEVELOPMENT') == 'true':
        return '123'
    return ''

def _auth(authorization: str = Header(None)) -> str:
    uid = _check_token(authorization)
    if not uid:
        raise HTTPException(401, 'invalid token')
    return uid

def _dg_params(output_format: str):
    if output_format == 'ulaw_8000':
        return {'encoding': 'mulaw', 'sample_rate': '8000', 'container': 'none'}, 'audio/basic'
    if output_format.startswith('mp3_'):
        return {'encoding': 'mp3', 'container': 'mp3'}, 'audio/mpeg'
    if output_format.startswith('pcm_'):
        return {'encoding': 'linear16', 'sample_rate': output_format.split('_',1)[1], 'container': 'none'}, 'audio/L16'
    return None, 'application/octet-stream'

@app.get('/docs')
def docs():
    return {'ok': True, 'service': 'omi-local-dev', 'tts': bool(DG_KEY), 'listen': bool(DG_KEY)}

@app.post('/v2/tts/synthesize')
async def synthesize(req: Req, uid: str = Depends(_auth)):
    if not DG_KEY:
        raise HTTPException(503, 'DEEPGRAM_API_KEY not configured')
    text = req.text.strip()
    if not text:
        raise HTTPException(400, 'empty text')
    params, media_type = _dg_params(req.output_format)
    if params is None:
        raise HTTPException(400, f'unsupported output_format: {req.output_format}')
    model = req.model_id if (req.model_id and str(req.model_id).startswith('aura')) else DG_DEFAULT_MODEL
    url = DEEPGRAM_SPEAK_URL + '?' + '&'.join(f'{k}={v}' for k,v in {**{'model':model}, **params}.items())
    headers = {'Content-Type': 'application/json', 'Authorization': f'Token {DG_KEY}'}
    client = httpx.AsyncClient(timeout=60.0)
    try:
        cm = client.stream('POST', url, json={'text': text}, headers=headers)
        resp = await cm.__aenter__()
        if resp.status_code >= 400:
            err = (await resp.aread()).decode('utf-8','replace')[:200]
            await cm.__aexit__(None,None,None); await client.aclose()
            log.warning('DG speak %s uid=%s: %s', resp.status_code, uid, err)
            raise HTTPException(resp.status_code, 'TTS upstream error')
    except HTTPException:
        raise
    except Exception as e:
        try: await client.aclose()
        except Exception: pass
        log.error('tts upstream: %s', e)
        raise HTTPException(502, 'TTS upstream unavailable')
    async def gen():
        try:
            async for chunk in resp.aiter_bytes(): yield chunk
        finally:
            try: await cm.__aexit__(None,None,None)
            except Exception: pass
            await client.aclose()
    return StreamingResponse(gen(), media_type=media_type)

def _listen_params(qs: dict) -> dict:
    """Map RN/Omi query params to Deepgram /v1/listen params."""
    def first(k, d=None):
        v = qs.get(k); return v[0] if isinstance(v, list) and v else (v if v else d)
    codec = (first('codec') or 'linear16').lower()
    sample_rate = str(first('sample_rate') or '16000')
    channels = str(first('channels') or '1')
    language = first('language') or 'en'
    # map wire codec names
    enc = codec
    if codec in ('pcm16', 'linear16'):
        enc = 'linear16'
    elif codec in ('pcm8', 'mulaw', 'ulaw'):
        enc = 'mulaw' if codec != 'pcm8' else 'linear16'  # pcm8 in omi naming is 8kHz pcm; be flexible
        if codec == 'pcm8' and sample_rate == '16000':
            enc = 'linear16'
    elif codec in ('opus', 'opus_fs320', 'opusfs320'):
        enc = 'opus'
    params = {
        'model': 'nova-2',
        'language': language,
        'encoding': enc,
        'sample_rate': sample_rate,
        'channels': channels,
        'punctuate': 'true',
        'interim_results': 'true',
        'smart_format': 'true',
        'utterance_end_ms': '1200',
        'vad_events': 'true',
    }
    # opus: Deepgram can infer container; be permissive
    return params

@app.websocket('/v4/listen')
async def listen_ws(websocket: WebSocket):
    qs = dict(websocket.query_params)
    uid = _check_token(qs.get('token'))
    if not uid:
        await websocket.close(code=4001, reason='unauthorized')
        return
    if not DG_KEY:
        await websocket.close(code=1011, reason='DEEPGRAM_API_KEY missing')
        return
    await websocket.accept()
    params = _listen_params(qs)
    dg_url = DEEPGRAM_LISTEN_URL + '?' + urlencode(params)
    log.info('listen start uid=%s params=%s', uid, {k:v for k,v in params.items() if k!='model'})

    async def client_to_dg(dg_ws):
        try:
            while True:
                msg = await websocket.receive()
                if 'bytes' in msg and msg['bytes'] is not None:
                    await dg_ws.send(msg['bytes'])
                elif 'text' in msg and msg['text'] is not None:
                    # forward control frames if any
                    try:
                        await dg_ws.send(msg['text'])
                    except Exception:
                        pass
                elif msg.get('type') == 'websocket.disconnect':
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.debug('client_to_dg: %s', e)
        finally:
            try:
                await dg_ws.send(json.dumps({'type': 'CloseStream'}))
            except Exception:
                pass

    async def dg_to_client(dg_ws):
        try:
            async for message in dg_ws:
                if isinstance(message, (bytes, bytearray)):
                    await websocket.send_bytes(bytes(message))
                else:
                    await websocket.send_text(message if isinstance(message, str) else message.decode('utf-8','replace'))
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            log.debug('dg_to_client: %s', e)
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    try:
        async with websockets.connect(
            dg_url,
            extra_headers={'Authorization': f'Token {DG_KEY}'},
            ping_interval=20, ping_timeout=20, close_timeout=5,
            max_size=16*1024*1024,
        ) as dg_ws:
            t1 = asyncio.create_task(client_to_dg(dg_ws))
            t2 = asyncio.create_task(dg_to_client(dg_ws))
            done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
    except Exception as e:
        log.warning('listen upstream uid=%s: %s', uid, e)
        try:
            await websocket.close(code=1011, reason='upstream error')
        except Exception:
            pass

@app.websocket('/v4/web/listen')
async def web_listen_ws(websocket: WebSocket):
    # delegate same behavior (dev)
    await listen_ws(websocket)



@app.get('/health')
@app.get('/v1/health')
def health():
    return {'status': 'ok', 'service': 'omi-local-dev'}

# Local-dev stubs: RN expects bare arrays / envelopes. Replace with real local
# stores (SQLite/on-device sync) as part of full localization.
@app.get('/v3/memories')
def memories(limit: int = 200, offset: int = 0):
    return []

@app.get('/v1/conversations')
def conversations(limit: int = 50, offset: int = 0):
    return []

@app.get('/v1/action-items')
@app.get('/v2/action-items')
def action_items(**kw):
    return {'action_items': [], 'items': []}

@app.get('/v1/goals')
def goals(**kw):
    return []

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
