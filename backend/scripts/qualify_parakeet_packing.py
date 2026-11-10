"""Run inside an isolated dev Parakeet image. Public fixture; no customer DB.

Usage: nice -n 19 python qualify_parakeet_packing.py --fixture public.wav
  --dcgm http://NODE_MATCHED_EXPORTER:9400/metrics --output /tmp/packing.json
Starts only the local ASR service. Receipts contain timing/shape, never text/audio.
"""

import argparse
import asyncio
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import wave
from collections import Counter

import httpx
import uvicorn

# This script runs only in the standalone Parakeet image.
sys.path.insert(0, '/app')
import main as service  # noqa: E402


def stats(values):
    values = sorted(values)
    return {'n': len(values), 'p95': values[math.ceil(0.95 * len(values)) - 1], 'max': max(values)} if values else None


async def qualify(args):
    raw = Path(args.fixture).read_bytes()
    with wave.open(io.BytesIO(raw)) as audio:
        rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
        pcm = audio.readframes(audio.getnframes())

    def wav(seconds):
        out = io.BytesIO()
        size = int(seconds * rate * channels * width)
        with wave.open(out, 'wb') as audio:
            audio.setframerate(rate)
            audio.setnchannels(channels)
            audio.setsampwidth(width)
            audio.writeframes((pcm * math.ceil(size / len(pcm)))[:size])
        return out.getvalue()

    payloads = {seconds: wav(seconds) for seconds in (24, 120, 360)}
    server = uvicorn.Server(
        uvicorn.Config(service.app, host='127.0.0.1', port=8080, access_log=False, log_level='warning')
    )
    server_task = asyncio.create_task(server.serve())
    receipt = {'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'waves': args.waves, 'steps': []}
    try:
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            for _ in range(900):
                if server_task.done():
                    await server_task
                    raise RuntimeError('server exited before ready')
                if service.gpu_worker is not None and service.gpu_worker.is_ready:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError('GPU did not become ready')

            async def post(lane, seconds):
                started = time.monotonic()
                headers = (
                    {'X-Omi-STT-Surface': 'live-window', 'X-Omi-STT-Timeout-Seconds': '3'} if lane == 'live' else {}
                )
                response = await client.post(
                    'http://127.0.0.1:8080/v1/transcribe',
                    headers=headers,
                    files={'file': ('public.wav', payloads[seconds], 'audio/wav')},
                )
                # Do not retain or print the body.
                nonempty = response.status_code == 200 and bool(response.json().get('text'))
                return {
                    'lane': lane,
                    'seconds': time.monotonic() - started,
                    'status': response.status_code,
                    'nonempty': nonempty,
                }

            await post('live', 24)  # warm-up excluded
            steps = () if args.long_only else ((False, 2), (True, 2), (True, 3))
            for packing, concurrency in steps:
                service._packing_enabled = packing
                service.batch_engine._packing = packing
                rows, dcgm = [], []
                stopped = asyncio.Event()

                async def sample():
                    while not stopped.is_set():
                        response = await client.get(args.dcgm)
                        values = [
                            float(line.rsplit(' ', 1)[1])
                            for line in response.text.splitlines()
                            if line.startswith('DCGM_FI_DEV_GPU_UTIL{')
                        ]
                        dcgm.append({'time': time.time(), 'values': values})
                        await asyncio.sleep(1)

                sampling = asyncio.create_task(sample())
                try:
                    for _ in range(args.waves):
                        start = time.monotonic()
                        rows.extend(
                            await asyncio.gather(
                                *(
                                    post(
                                        'live' if i < math.ceil(concurrency / 2) else 'backfill',
                                        24 if i < math.ceil(concurrency / 2) else 120,
                                    )
                                    for i in range(concurrency)
                                )
                            )
                        )
                        await asyncio.sleep(max(0, 3 - (time.monotonic() - start)))
                    # Sustained final load crosses exporter collection boundaries.
                    final_start = time.time()

                    async def pressure():
                        while time.time() - final_start < 15:
                            await post('backfill', 120)

                    await asyncio.gather(*(pressure() for _ in range(concurrency)))
                finally:
                    stopped.set()
                    await sampling
                step = {
                    'packing': packing,
                    'concurrency': concurrency,
                    'delivery': stats([r['seconds'] for r in rows]),
                    'live_delivery': stats([r['seconds'] for r in rows if r['lane'] == 'live']),
                    'statuses': dict(Counter(str(r['status']) for r in rows)),
                    'empty_successes': sum(not r['nonempty'] for r in rows),
                    'dcgm_nonzero': any(v > 0 for sample in dcgm[-10:] for v in sample['values']),
                    'requests': rows,
                    'dcgm': dcgm,
                }
                step['passes'] = (
                    step['delivery']['p95'] < 3
                    and step['dcgm_nonzero']
                    and step['statuses'] == {'200': len(rows)}
                    and not step['empty_successes']
                )
                receipt['steps'].append(step)
                Path(args.output).write_text(json.dumps(receipt, indent=2))
                print(json.dumps({k: v for k, v in step.items() if k not in ('requests', 'dcgm')}), flush=True)
            if args.long_only:
                service._packing_enabled = True
                service.batch_engine._packing = True
                historical = asyncio.create_task(post('backfill', 360))
                # Launch live after historical work has entered the service.
                for _ in range(100):
                    if service.ACTIVE_BATCH._value.get() > 0:
                        break
                    await asyncio.sleep(0.01)
                probes = []
                for _ in range(6):
                    probes.append(await post('live', 24))
                    await asyncio.sleep(0.25)
                long_result = await historical
                v2 = await client.post(
                    'http://127.0.0.1:8080/v2/transcribe',
                    data={'diarize': 'false'},
                    files={'file': ('public.wav', payloads[360], 'audio/wav')},
                )
                receipt['long_backfill'] = {
                    'historical': long_result,
                    'live': probes,
                    'live_delivery': stats([r['seconds'] for r in probes]),
                    'v2_status': v2.status_code,
                    'v2_nonempty': v2.status_code == 200 and bool(v2.json().get('text')),
                    'v2_latest_segment_end': max((s.get('end', 0) for s in v2.json().get('segments', [])), default=0),
                }
                print(json.dumps(receipt['long_backfill']), flush=True)
            receipt['decoder_graph_allowed'] = (
                service.gpu_worker._model.decoding.decoding.decoding_computer.allow_cuda_graphs
            )
            Path(args.output).write_text(json.dumps(receipt, indent=2))
    finally:
        server.should_exit = True
        await server_task


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--dcgm', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--waves', type=int, default=40)
    parser.add_argument('--long-only', action='store_true')
    asyncio.run(qualify(parser.parse_args()))
