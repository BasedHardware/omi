"""Canonical alias module for ``database.v17_vector_repair_outbox`` (WS-G).

New canonical-path code may import from here; the V17 module name remains valid
until a later rename wave. No behavior change — re-exports only.
"""

from database.v17_vector_repair_outbox import (
    V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE,
    V17_VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION,
    build_v17_vector_repair_purge_outbox_records,
    write_v17_vector_repair_purge_outbox_records,
)

__all__ = [
    "V17_VECTOR_REPAIR_PURGE_OUTBOX_EVENT_TYPE",
    "V17_VECTOR_REPAIR_PURGE_OUTBOX_SCHEMA_VERSION",
    "build_v17_vector_repair_purge_outbox_records",
    "write_v17_vector_repair_purge_outbox_records",
]
