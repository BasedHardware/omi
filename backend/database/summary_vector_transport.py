"""Single-attempt, cancellable Pinecone requests for optional owner summaries only."""

import asyncio
from copy import copy
from functools import partial
from typing import Any

from pinecone import Pinecone

from config.summary_context import context_stage


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
                config.retries = None
                controller: Any = Pinecone(api_key=self.index._config.api_key)
                # 7.3.0 rejects the retired openapi_config constructor keyword.
                # This is a new private controller, never the shared one.
                controller._openapi_config = config
                async with controller.IndexAsyncio(host=self.index._config.host) as client:
                    # Pinned 7.3.0 has no public redirect option. This handle is
                    # private to one summary request; redirects must not add IO.
                    transport: Any = client._api_client.rest_client._retry_client
                    transport._retry_options = type(transport._retry_options)(attempts=1)
                    transport.request = partial(transport.request, allow_redirects=False)
                    return await client.query(**kwargs)

        with context_stage('vector'):
            return asyncio.run(request())
