"""Process-local ingest signals. Durable aggregates remain the source of truth."""

from prometheus_client import Counter

CLIENT_TELEMETRY_INGEST_TOTAL = Counter(
    "omi_client_telemetry_ingest_events_total",
    "Complementary client-telemetry ingest outcomes. Accepted counters live in Firestore, not here.",
    ["result"],
)


def record_ingest(result: str) -> None:
    try:
        CLIENT_TELEMETRY_INGEST_TOTAL.labels(result=result).inc()
    except Exception:
        return
