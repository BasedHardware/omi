"""Single-attempt, cancellable Pinecone requests for optional owner summaries only."""

import asyncio
from copy import copy
from functools import partial
from typing import Any

from aiohttp_retry import ExponentialRetry
from pinecone.db_data import IndexAsyncio


class SummaryVectorIndex:
    """Keep owner routing outside the transport; never mutate the shared index."""

    def __init__(self, index: Any):
        self.index = index

    def query(self, *, _request_timeout: float, **kwargs: Any) -> Any:
        async def request() -> Any:
            # Pinecone 7.3.0's aiohttp transport ignores _request_timeout. The
            # outer cancellation scope bounds connection, response body and cleanup.
            async with asyncio.timeout(_request_timeout):
                config = copy(self.index._openapi_config)
                config.retries = ExponentialRetry(attempts=1)
                async with IndexAsyncio(
                    api_key=self.index._config.api_key,
                    host=self.index._config.host,
                    openapi_config=config,
                ) as client:
                    # Pinned 7.3.0 has no public redirect option. This handle is
                    # private to one summary request; redirects must not add IO.
                    transport: Any = client._api_client.rest_client._retry_client
                    transport.request = partial(transport.request, allow_redirects=False)
                    return await client.query(**kwargs)

        return asyncio.run(request())
