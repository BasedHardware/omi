"""Run an SDK query at an explicit snapshot using the existing client and probe."""

from typing import Any, Iterator

from google.cloud.firestore_v1.base_query import _query_response_to_snapshot  # pyright: ignore[reportPrivateUsage]

from database.firestore_document_probe import observe_query_stream


def stream_at_read_time(query: Any, read_time: Any, *, timeout: float, caller: str) -> Iterator[Any]:
    # The pinned high-level Query.stream has no read_time parameter. Reuse its
    # query encoding, transport and snapshot decoder for the same RunQuery RPC.
    request, prefix, _ = query._prep_stream(None, None, timeout)
    del request['transaction']
    request['read_time'] = read_time
    client = query._client

    def rows():
        responses = client._firestore_api.run_query(
            request=request, metadata=client._rpc_metadata, timeout=timeout, retry=None
        )
        for response in responses:
            snapshot = _query_response_to_snapshot(response, query._parent, prefix)
            if snapshot is not None:
                yield snapshot

    return observe_query_stream(query, rows(), caller=caller)
