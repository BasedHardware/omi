"""The live upload wait has a deadline; its workers can never commit receipts."""

import asyncio
import random
import time
from concurrent.futures import Future
from typing import Callable

from config.gcs_transport import UploadWaitTimeout, transport_cause

from utils.executors import storage_executor, submit_with_context
from utils.observability.held_content import record_publication_retry, record_staging_retry
from utils.sync.live_cap_publication import Publication

UPLOAD_ATTEMPT_SECONDS = 4.0
UPLOAD_SOCKET_SECONDS = 1.5
UPLOAD_ATTEMPTS = 2
UPLOAD_TOTAL_SECONDS = 8.0


def transient(error: BaseException) -> bool:
    """GCS transport and HTTP retry policy; permanent 4xx never retry."""
    code = getattr(error, 'code', None)
    response = getattr(error, 'response', None)
    code = getattr(response, 'status_code', code)
    if isinstance(code, int):
        return code in (408, 429) or 500 <= code <= 599
    return transport_cause(error) is not None or isinstance(error, ConnectionResetError)


async def prepare(source: Publication, upload: Callable[[], dict]) -> None:
    """Exactly two upload-only attempts for this identity, including later flushes.

    A Requests timeout bounds socket inactivity, not wall time. Bound each wait
    too, including executor queueing, encoding, fences, upload and 412 reload.
    Shield the future: a late put may land, and must keep its scratch and result.
    Workers own neither Publication state nor any Firestore commit. Both puts
    use generation zero, so overlap can only create one immutable object.
    """
    if source.fields:
        return
    last_error: BaseException | None = None
    # A later flush can adopt a completed late upload without starting a third.
    for previous in source.upload_attempts:
        if previous.done():
            try:
                source.fields = previous.result()
            except Exception as error:
                last_error = error
            else:
                return
    if last_error is not None and not transient(last_error):
        raise last_error
    if len(source.upload_attempts) == UPLOAD_ATTEMPTS:
        raise last_error or UploadWaitTimeout('immutable live upload outcome unknown')
    if source.upload_attempts and last_error is None:
        # A cancelled waiter is not a transport failure. Preserve its pending
        # upload; a later flush may adopt its result, but cannot duplicate it.
        raise UploadWaitTimeout('immutable live upload outcome unknown')
    until = time.monotonic() + UPLOAD_TOTAL_SECONDS
    while len(source.upload_attempts) < UPLOAD_ATTEMPTS:
        if source.upload_attempts:
            await asyncio.sleep(min(0.2 * 2 ** (len(source.upload_attempts) - 1), 1.0) * random.uniform(0.5, 1.5))
        source.put_started = True
        future: Future[dict] = submit_with_context(storage_executor, upload)
        source.upload_attempts.append(future)
        deadline = asyncio.timeout(max(0, min(UPLOAD_ATTEMPT_SECONDS, until - time.monotonic())))
        try:
            async with deadline:
                await asyncio.shield(asyncio.wrap_future(future))
                # The wrapper owns the wait; the retained future owns the result.
                fields = future.result()
        except asyncio.TimeoutError:
            if not deadline.expired():
                raise  # An operation's bare TimeoutError is not a transport retry.
            last_error = UploadWaitTimeout('immutable live upload wait deadline')
        except Exception as error:
            last_error = error
        else:
            source.fields = fields
            if len(source.upload_attempts) > 1:
                record_publication_retry('retried_ok', transport_cause(last_error) or 'timeout')
                record_staging_retry('retried_ok')
            return
        if not transient(last_error):
            record_staging_retry('permanent')
            raise last_error
    record_publication_retry('exhausted', transport_cause(last_error) or 'timeout')
    record_staging_retry('exhausted')
    raise last_error or UploadWaitTimeout('immutable live upload outcome unknown')
