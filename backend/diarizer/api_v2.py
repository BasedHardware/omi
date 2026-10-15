"""GPU-independent HTTP admission; injected inference supports hermetic tests."""

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request

from admission import AdmissionQueue, CapacityExceeded
from metrics import DEPTH, REQUESTS

MAX_AUDIO_SECONDS = 7200


def create_router(worker, queue=None):
    queue = queue or AdmissionQueue()
    router = APIRouter()

    async def diarization_v2(
        request: Request,
        min_speakers: int | None = Query(None, ge=1, le=100),
        max_speakers: int | None = Query(None, ge=1, le=100),
    ):
        if min_speakers and max_speakers and min_speakers > max_speakers:
            raise HTTPException(422, 'min_speakers exceeds max_speakers')
        admitted = False
        job = None
        try:
            queue.reserve()
            admitted = True
            DEPTH.set(queue.depth)
            body = bytearray()
            while True:
                message = await request.receive()
                if message['type'] == 'http.disconnect':
                    raise HTTPException(400, 'upload disconnected')
                chunk = message.get('body', b'')
                if len(body) + len(chunk) > MAX_AUDIO_SECONDS * 32000 + 65536:
                    raise HTTPException(413, 'audio exceeds two hours')
                body.extend(chunk)
                if not message.get('more_body', False):
                    break
            content_type = request.headers.get('content-type', '').split(';')[0]
            job = asyncio.get_running_loop().run_in_executor(
                queue.executor, worker, body, content_type, min_speakers, max_speakers
            )

            # Inference owns admission once submitted. Repeated client/task
            # cancellation cannot grow the executor's internal queue unboundedly.
            def completed(_future):
                queue.release()
                DEPTH.set(queue.depth)

            job.add_done_callback(completed)
            result = await asyncio.shield(job)
            REQUESTS.labels(outcome='ok').inc()
            return result
        except CapacityExceeded:
            REQUESTS.labels(outcome='rejected').inc()
            raise HTTPException(429, 'diarization queue full', headers={'Retry-After': '30'}) from None
        except Exception:
            REQUESTS.labels(outcome='failed').inc()
            raise
        finally:
            if admitted and job is None:
                queue.release()
            DEPTH.set(queue.depth)

    router.add_api_route('/v2/diarization', diarization_v2, methods=['POST'])
    return router
