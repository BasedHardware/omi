"""Complete bounded filtered reads using the existing mixed-memory policies."""

from typing import Any, Optional

from database.mcp_memory_queries import read_mcp_memory_candidates, MCP_FILTER_SCAN_LIMIT
from utils.memory.canonical_memory_adapter import read_canonical_scan_page
from utils.mcp_memories import filter_and_sort_memories, memory_timestamp
from utils.mcp_server.errors import ToolExecutionError
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


def collect_filtered_mcp_memories(
    service: Any,
    uid: str,
    *,
    filters: dict,
    budget: Optional[ListReadBudget] = None,
    max_candidates: int = MCP_FILTER_SCAN_LIMIT,
) -> tuple[list[dict], int]:
    max_candidates = max(1, min(max_candidates, MCP_FILTER_SCAN_LIMIT))
    db_client = service.db_client
    rows = []
    scanned_count = 0
    for origin in ('memory_items', 'memories'):
        try:
            snapshots = read_mcp_memory_candidates(
                uid,
                origin=origin,
                filters=filters,
                firestore_client=db_client,
                max_candidates=max_candidates,
                **({'budget': budget} if budget is not None else {}),
            )
        except ListReadBudgetExhausted as exc:
            raise ToolExecutionError(
                'memory_filter_window_exceeded: request read budget exhausted; narrow the filter.',
                code=-32009,
                http_status=503,
            ) from exc
        if len(snapshots) > max_candidates:
            raise ToolExecutionError(
                f'memory_filter_window_exceeded: narrow updated_after or other filters; no complete page can be established within {max_candidates} candidates per store.',
                code=-32009,
                http_status=413,
            )
        scanned_count += len(snapshots)
        if origin == 'memory_items':
            for offset in range(0, len(snapshots), 100):
                chunk = snapshots[offset : offset + 100]
                slots, _ = read_canonical_scan_page(
                    uid, limit=len(chunk), db_client=db_client, candidate_snapshots=chunk, budget=budget
                )
                rows.extend(memory.model_dump(mode='json') for memory, _cursor in slots if memory is not None)
        else:
            # Keep identity/state suppression authoritative even when a canonical
            # twin does not satisfy this request's candidate predicates.
            for offset in range(0, len(snapshots), 100):
                chunk = snapshots[offset : offset + 100]
                try:
                    statuses = service.canonical_statuses(
                        uid, [snapshot.id for snapshot in chunk], **({"budget": budget} if budget is not None else {})
                    )
                except ListReadBudgetExhausted as exc:
                    raise ToolExecutionError(
                        'memory_filter_window_exceeded: request read budget exhausted during suppression checks; narrow the filter.',
                        code=-32009,
                        http_status=503,
                    ) from exc
                for snapshot in chunk:
                    if service.historical_suppression_reason(snapshot.id, statuses=statuses):
                        continue
                    raw = dict(snapshot.to_dict() or {})
                    raw['id'] = snapshot.id
                    slots = service.history.adapt_scan_payloads(
                        uid, [raw], [(raw.get('updated_at'), snapshot.id)], device_scope_request=None
                    )
                    if slots and slots[0][0] is not None:
                        rows.append(slots[0][0].memory.model_dump(mode='json'))
    if budget is not None and budget.truncated:
        raise ToolExecutionError(
            'memory_filter_window_exceeded: request read budget exhausted during policy checks; narrow the filter.',
            code=-32009,
            http_status=503,
        )
    # The compatibility scoring order is the universal newest-updated view,
    # including created-only historical rows, not canonical-store-first order.
    rows.sort(
        key=lambda row: (
            -(memory_timestamp(row.get('updated_at')) or memory_timestamp(row.get('created_at')) or float('-inf')),
            str(row.get('id') or ''),
        )
    )
    return filter_and_sort_memories(rows, **filters), scanned_count
