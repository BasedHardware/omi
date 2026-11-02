"""Best-effort, process-local Pinecone query accounting with closed label sets.

Kept independent of utils.metrics so the provider boundary does not import the
application metrics graph. All application exporters use the default registry.
"""

from collections.abc import Mapping
from typing import Any

from prometheus_client import Counter

FAMILIES = frozenset({'ns1', 'ns2', 'ns3', 'ns4', 'ns_x', 'ns_tchunks', 'workstream-association-v1'})
CALLERS = frozenset(
    {
        'query_vectors',
        'query_vectors_by_metadata',
        'query_workstream_association_candidates',
        'find_similar_memories',
        'query_memory_vector_candidates',
        'find_similar_x_posts',
        'search_screen_activity_vectors',
        'search_action_items_by_vector',
        'find_similar_action_items',
        'search_transcript_chunks',
        'account_purge_verify',
    }
)

QUERIES = Counter(
    'omi_pinecone_queries_total',
    'Pinecone provider query attempts by shared namespace family, routed mode and bounded caller',
    ['family', 'route_mode', 'caller'],
)
READ_UNITS = Counter(
    'omi_pinecone_read_units_total',
    'Pinecone read units reported on successful query responses',
    ['family', 'route_mode', 'caller'],
)
MISSING_USAGE = Counter(
    'omi_pinecone_query_missing_usage_total',
    'Successful Pinecone queries without read-unit usage; no units are inferred',
    ['family', 'route_mode', 'caller'],
)
METERING_ERRORS = Counter('omi_pinecone_query_metering_errors_total', 'Swallowed Pinecone query metering errors')


def record_metering_error() -> None:
    try:
        METERING_ERRORS.inc()
    except Exception:
        pass


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def record_query(family: str, routed_namespace: str, caller: str, response: Any, *, succeeded: bool) -> None:
    """No network, logs, retries or owner labels; never affect provider outcomes."""
    try:
        labels = (
            family if family in FAMILIES else 'other',
            'legacy' if routed_namespace == family else 'partitioned',
            caller if caller in CALLERS else 'other',
        )
        QUERIES.labels(*labels).inc()
        if not succeeded:
            return
        units = _field(_field(response, 'usage'), 'read_units')
        if units is None:
            MISSING_USAGE.labels(*labels).inc()
            return
        # The pinned 7.3.0 SDK's Usage.read_units schema is integer-only.
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise ValueError('Invalid Pinecone read-unit usage')
        READ_UNITS.labels(*labels).inc(units)
    except Exception:
        record_metering_error()
