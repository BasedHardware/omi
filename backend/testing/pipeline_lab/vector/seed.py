"""Seed the start state's vectors so real retrieval and dedup paths have data (L7).

Without this, ``find_similar_action_items`` returns nothing (notes task dedup goes
quiet), memory retrieval loses its vector half and chat skips semantic search.

The plan is pure: which records, under which ids, namespaces and metadata, built
from the seeded rows. :func:`apply_with_product` writes it through the product's own
``database.vector_db`` upsert helpers (same ids, metadata and embedding inputs as
production). :func:`apply_direct` writes the identical records straight into a
:class:`NumericVectorIndex`, for tests and for a stack without product imports.

Known gaps against production, reported in ``SeedReport.gaps``:
- ns1 conversation metadata (people/topics/entities/dates) is produced by an LLM in
  production and is not in the snapshot; seeded rows carry only ``created_at``.
- canonical (ledger) memory vectors need ``MemoryItem`` ledger fields the portable
  export does not keep; memories are seeded with the batch (``upsert_memory_vectors_batch``)
  shape instead.
- transcript chunks (``ns_tchunks``) are not seeded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from testing.pipeline_lab.stack.io import parse_time

CONVERSATIONS_NAMESPACE = 'ns1'
MEMORIES_NAMESPACE = 'ns2'
ACTION_ITEMS_NAMESPACE = 'ns4'


@dataclass
class VectorRecord:
    namespace: str
    vector_id: str
    text: str
    metadata: dict[str, Any]
    source_id: str


@dataclass
class SeedReport:
    planned: dict[str, int] = field(default_factory=dict)
    written: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {'planned': self.planned, 'written': self.written, 'skipped': self.skipped, 'gaps': self.gaps}


def structured_text(structured: Mapping[str, Any] | None) -> str:
    """The production embedding input for ns1: ``str(conversation.structured)``."""
    if not structured:
        return ''
    try:
        from models.structured import Structured

        return str(Structured.model_validate(dict(structured)))
    except Exception:
        import json

        return json.dumps(dict(structured), sort_keys=True, ensure_ascii=False)


def _ts(value: Any) -> int | None:
    parsed = parse_time(value)
    return int(parsed.timestamp()) if parsed else None


def plan_vectors(
    uid: str,
    *,
    conversations: Iterable[Mapping[str, Any]] = (),
    memories: Iterable[Mapping[str, Any]] = (),
    action_items: Iterable[Mapping[str, Any]] = (),
    text_for_structured: Callable[[Mapping[str, Any] | None], str] = structured_text,
) -> tuple[list[VectorRecord], SeedReport]:
    report = SeedReport()
    records: list[VectorRecord] = []

    def skip(kind: str) -> None:
        report.skipped[kind] = report.skipped.get(kind, 0) + 1

    for row in conversations:
        structured = row.get('structured') or {}
        if row.get('discarded') or not (structured.get('title') or structured.get('overview')):
            skip('conversations')
            continue
        metadata: dict[str, Any] = {'uid': uid, 'memory_id': row['id']}
        created = _ts(row.get('created_at') or row.get('started_at'))
        if created is not None:
            metadata['created_at'] = created
        records.append(
            VectorRecord(
                CONVERSATIONS_NAMESPACE, f'{uid}-{row["id"]}', text_for_structured(structured), metadata, row['id']
            )
        )
    for row in memories:
        content = (row.get('content') or '').strip()
        if not content or row.get('deleted') or row.get('invalid_at') or row.get('superseded_by'):
            skip('memories')
            continue
        metadata = {'uid': uid, 'memory_id': row['id'], 'category': row.get('category') or 'other'}
        created = _ts(row.get('created_at'))
        if created is not None:
            metadata['created_at'] = created
        if row.get('subject_entity_id'):
            metadata['subject_entity_id'] = row['subject_entity_id']
        records.append(VectorRecord(MEMORIES_NAMESPACE, f'{uid}-{row["id"]}', content, metadata, row['id']))
    for row in action_items:
        description = (row.get('description') or '').strip()
        if not description or row.get('deleted'):
            skip('action_items')
            continue
        metadata = {'uid': uid, 'action_item_id': row['id']}
        created = _ts(row.get('created_at'))
        if created is not None:
            metadata['created_at'] = created
        records.append(VectorRecord(ACTION_ITEMS_NAMESPACE, f'{uid}-ai-{row["id"]}', description, metadata, row['id']))
    for record in records:
        report.planned[record.namespace] = report.planned.get(record.namespace, 0) + 1
    report.gaps = [
        'ns1 metadata (people/topics/entities/dates) not seeded: production derives it with an LLM',
        'ns2 seeded in batch shape, not canonical ledger shape',
        'ns_tchunks transcript chunks not seeded',
    ]
    return records, report


def apply_direct(
    records: Sequence[VectorRecord], index: Any, embedder: Any, report: SeedReport, *, batch: int = 64
) -> SeedReport:
    """Embed and upsert the planned records straight into ``index``."""
    by_namespace: dict[str, list[VectorRecord]] = {}
    for record in records:
        by_namespace.setdefault(record.namespace, []).append(record)
    for namespace, items in by_namespace.items():
        for start in range(0, len(items), batch):
            chunk = items[start : start + batch]
            vectors = embedder.embed([item.text for item in chunk])
            index.upsert(
                vectors=[
                    {'id': item.vector_id, 'values': values, 'metadata': item.metadata}
                    for item, values in zip(chunk, vectors)
                ],
                namespace=namespace,
            )
            report.written[namespace] = report.written.get(namespace, 0) + len(chunk)
    return report


def apply_with_product(records: Sequence[VectorRecord], uid: str, report: SeedReport, *, batch: int = 64) -> SeedReport:
    """Write through ``database.vector_db`` (needs the lab env, index and embeddings installed)."""
    from database import vector_db
    from utils.llm import clients

    for record in (r for r in records if r.namespace == CONVERSATIONS_NAMESPACE):
        vector = clients.generate_embedding(record.text)
        metadata = {key: value for key, value in record.metadata.items() if key not in ('uid', 'memory_id')}
        if vector_db.upsert_vector2(uid, record.source_id, vector, metadata):
            report.written[record.namespace] = report.written.get(record.namespace, 0) + 1
    memories = [r for r in records if r.namespace == MEMORIES_NAMESPACE]
    for start in range(0, len(memories), batch):
        chunk = memories[start : start + batch]
        written = vector_db.upsert_memory_vectors_batch(
            uid,
            [
                {
                    'memory_id': r.source_id,
                    'content': r.text,
                    'category': r.metadata.get('category', 'other'),
                    'subject_entity_id': r.metadata.get('subject_entity_id'),
                }
                for r in chunk
            ],
        )
        report.written[MEMORIES_NAMESPACE] = report.written.get(MEMORIES_NAMESPACE, 0) + int(written or 0)
    tasks = [r for r in records if r.namespace == ACTION_ITEMS_NAMESPACE]
    for start in range(0, len(tasks), batch):
        chunk = tasks[start : start + batch]
        written = vector_db.upsert_action_item_vectors_batch(
            uid, [{'action_item_id': r.source_id, 'description': r.text} for r in chunk]
        )
        report.written[ACTION_ITEMS_NAMESPACE] = report.written.get(ACTION_ITEMS_NAMESPACE, 0) + int(written or 0)
    return report
