"""Bounded renewal and cancellation custody for paid synchronous work."""

import asyncio
from time import monotonic
from database import conversations_v3_leases as leases
from utils.executors import db_executor, run_blocking, start_background_task

MAX_RENEWAL_SECONDS = 900


async def renew_until_done(uid, key, token, worker):
    deadline = monotonic() + MAX_RENEWAL_SECONDS
    while not worker.done():
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise RuntimeError('v3_lease_lifetime_exhausted')
        done, _ = await asyncio.wait({worker}, timeout=min(leases.LEASE_SECONDS / 3, remaining))
        if done:
            return
        for attempt in range(3):
            if monotonic() >= deadline:
                raise RuntimeError('v3_lease_lifetime_exhausted')
            try:
                await run_blocking(db_executor, leases.renew, uid, key, token)
                break
            except leases.Conflict:
                raise
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)


async def leased_work(uid, key, token, executor, fn, *args):
    # The paid call's caller owns the Cloud Tasks retry, so a transient provider
    # fault is logged as a bounded WARNING instead of the provider body at ERROR.
    worker = start_background_task(
        run_blocking(executor, fn, *args), name='v3-paid-work', bounded_provider_failure=True
    )
    keeper = start_background_task(renew_until_done(uid, key, token, worker), name='v3-paid-lease')
    try:
        return await asyncio.shield(worker)
    finally:
        # The caller's cancellation never releases custody of a running thread.
        try:
            await asyncio.shield(worker)
        finally:
            await keeper
