"""Copy, reconcile and qualify one owner's vectors before an atomic cutover.

This is an operator service, never a request-time fallback. The source remains
authoritative until both provider freshness and a quiet revision are proven.
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import time
from typing import Any, Iterator
from uuid import uuid4

import httpx

from database import pinecone_partition_state as state
from database.legal_holds import external_write_fence
from database.pinecone_provider_errors import BARRIER_ID, barrier_record, is_missing_namespace


class MigrationNotReady(RuntimeError):
    """A failed qualification leaves the old route active."""


def bounded_upsert_batches(records: list[dict], namespace: str) -> Iterator[list[dict]]:
    """Keep wide vectors and metadata below Pinecone's 2 MB request limit."""
    overhead = len(json.dumps({'namespace': namespace, 'vectors': []}).encode())
    batch: list[dict] = []
    size = overhead
    for record in records:
        encoded_size = len(json.dumps(record, allow_nan=False).encode()) + 2
        if overhead + encoded_size > 1_800_000:
            raise MigrationNotReady('Individual vector exceeds the safe upload size')
        if batch and (size + encoded_size > 1_800_000 or len(batch) == 1000):
            yield batch
            batch, size = [], overhead
        batch.append(record)
        size += encoded_size
    if batch:
        yield batch


def record_digest(record: dict) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    if record.get('sparseValues') or record.get('sparse_values'):
        raise MigrationNotReady('Sparse record migration is not qualified')
    payload = normalize({key: record[key] for key in ('id', 'values', 'metadata')})
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


IDENTITY_FIELDS = {
    'ns1': ('memory_id',),
    'ns2': ('memory_id',),
    'ns3': ('screenshot_id',),
    'ns4': ('action_item_id',),
    'ns_x': ('post_id',),
    'ns_tchunks': ('conversation_id', 'chunk_index'),
    'workstream-association-v1': ('workstream_id', 'account_generation'),
}


class PartitionTransport:
    """REST transport retains LSN headers that the normal SDK hides."""

    def __init__(self, host: str, api_key: str, *, client: httpx.Client | None = None):
        if not host.endswith('.pinecone.io') or '/' in host:
            raise ValueError('Expected an index host from the Pinecone control plane')
        self.host = host
        self.client = client or httpx.Client(timeout=60)
        self.headers = {'Api-Key': api_key, 'X-Pinecone-Api-Version': '2025-10'}
        self.read_units = 0.0
        self.write_units = 0.0

    def call(self, path: str, payload: dict) -> tuple[dict, dict]:
        response = self.client.post(f'https://{self.host}/{path}', json=payload, headers=self.headers)
        response.raise_for_status()
        body = response.json()
        usage = body.get('usage') or {}
        self.read_units += usage.get('readUnits', 0)
        self.write_units += usage.get('writeUnits', 0)
        return body, dict(response.headers)

    def owned_pages(self, namespace: str, uid: str) -> Iterator[list[dict]]:
        token = None
        seen_tokens: set[str] = set()
        while True:
            payload = {'namespace': namespace, 'filter': {'uid': {'$eq': uid}}, 'limit': 100}
            if token:
                payload['paginationToken'] = token
            try:
                body, _ = self.call('vectors/fetch_by_metadata', payload)
            except Exception as error:
                if not token and is_missing_namespace(error):
                    yield []
                    return
                raise
            records = list(body['vectors'].values())
            if any(record.get('metadata', {}).get('uid') != uid for record in records):
                raise MigrationNotReady('Provider returned a different owner')
            yield records
            token = (body.get('pagination') or {}).get('next')
            if not token:
                return
            if token in seen_tokens:
                raise MigrationNotReady('Provider repeated a pagination token')
            seen_tokens.add(token)

    def write(self, path: str, namespace: str, **payload: Any) -> int:
        try:
            _, headers = self.call(path, {'namespace': namespace, **payload})
        except Exception as error:
            if path == 'vectors/delete' and is_missing_namespace(error):
                return 0
            raise
        lsn = headers.get('x-pinecone-request-lsn')
        if lsn is None:
            raise MigrationNotReady('Pinecone did not return a write freshness receipt')
        return int(lsn)

    def query(self, namespace: str, uid: str, vector: list[float], top_k: int = 10) -> tuple[dict, int]:
        body, headers = self.call(
            'query',
            {
                'namespace': namespace,
                'filter': {'uid': {'$eq': uid}},
                'vector': vector,
                'topK': top_k,
                'includeMetadata': True,
            },
        )
        raw_lsn = headers.get('x-pinecone-max-indexed-lsn')
        if raw_lsn is None:
            if body['matches']:
                raise MigrationNotReady('Pinecone did not return query freshness')
            raw_lsn = 0
        if any(item.get('metadata', {}).get('uid') != uid for item in body['matches']):
            raise MigrationNotReady('Query returned another owner')
        return body, int(raw_lsn)

    def await_indexed(self, namespace: str, uid: str, vector: list[float], lsn: int) -> int:
        deadline = time.monotonic() + 60
        while True:
            _, indexed = self.query(namespace, uid, vector, top_k=1)
            if indexed >= lsn:
                return indexed
            if time.monotonic() >= deadline:
                raise MigrationNotReady('Pinecone freshness did not catch up within 60 seconds')
            time.sleep(1)

    def fresh_inventory(
        self, namespace: str, uid: str, vector: list[float], lsn: int, groups: dict | None = None
    ) -> set[str]:
        # Metadata-fetch pages have no freshness header. Qualify their complete
        # ID set against a fresh query, not just equal counts or sampled hits.
        # Reaching the provider cap cannot establish completeness.
        body, headers = self.call(
            'query',
            {
                'namespace': namespace,
                'filter': {'uid': {'$eq': uid}},
                'vector': vector,
                'topK': 10000,
                'includeMetadata': False,
            },
        )
        if int(headers.get('x-pinecone-max-indexed-lsn', 0 if lsn == 0 else -1)) < lsn:
            raise MigrationNotReady('Inventory query replica is stale')
        matches = body['matches']
        if len(matches) >= 10000:
            if not groups:
                raise MigrationNotReady('Owner exceeds complete-query limit; requires bounded inventory qualification')
            self.verify_no_unknown_identities(namespace, uid, vector, lsn, groups)
            # Every known identity is separately checked with complete payloads
            # below. Complement queries prove there are no unknown identities.
            return {vector_id for records in groups.values() for vector_id in records}
        ids = {item['id'] for item in matches}
        if len(ids) != len(matches):
            raise MigrationNotReady('Inventory query repeated an ID')
        return ids

    def verify_no_unknown_identities(
        self, namespace: str, uid: str, probe: list[float], lsn: int, groups: dict
    ) -> None:
        selectors = [json.loads(selector) for selector in groups]
        fields = tuple(sorted(selectors[0]))
        if any(tuple(sorted(selector)) != fields for selector in selectors):
            raise MigrationNotReady('Mixed identity schemas cannot prove a complete inventory')

        def absent(clauses: list[dict]) -> None:
            body, headers = self.call(
                'query',
                {
                    'namespace': namespace,
                    'vector': probe,
                    'topK': 1,
                    'includeMetadata': False,
                    'filter': {'$and': [{'uid': {'$eq': uid}}, *clauses]},
                },
            )
            if int(headers.get('x-pinecone-max-indexed-lsn', -1)) < lsn or body['matches']:
                raise MigrationNotReady('Fresh inventory contains an unknown identity or replica is stale')

        def visit(rows: list[dict], depth: int, prefix: list[dict]) -> None:
            field = fields[depth]
            children: dict[Any, list[dict]] = {}
            for row in rows:
                value = row[field]['$eq']
                if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                    raise MigrationNotReady('Identity filter requires a scalar source identity')
                children.setdefault(value, []).append(row)
            values = list(children)
            absent([*prefix, {field: {'$exists': False}}])
            # Pinecone bounds each $nin array; multiple AND clauses preserve
            # the exact complement without the query's 10k result truncation.
            absent([*prefix, *[{field: {'$nin': values[i : i + 10000]}} for i in range(0, len(values), 10000)]])
            if depth + 1 < len(fields):
                for value, child_rows in children.items():
                    visit(child_rows, depth + 1, [*prefix, {field: {'$eq': value}}])

        visit(selectors, 0, [])

    def verify_payloads(self, namespace: str, uid: str, probe: list[float], lsn: int, groups: dict) -> None:
        selectors, expected = [], {}

        def check() -> None:
            if not selectors:
                return
            body, headers = self.call(
                'query',
                {
                    'namespace': namespace,
                    'filter': {'$and': [{'uid': {'$eq': uid}}, {'$or': selectors}]},
                    'vector': probe,
                    'topK': len(expected) + 1,
                    'includeMetadata': True,
                    'includeValues': True,
                },
            )
            if int(headers.get('x-pinecone-max-indexed-lsn', -1)) < lsn:
                raise MigrationNotReady('Payload query replica is stale')
            actual = {item['id']: record_digest(item) for item in body['matches']}
            if actual != expected:
                raise MigrationNotReady('Fresh vector values or metadata differ from the copied snapshot')

        for selector_json, records in groups.items():
            if len(records) > 30:
                raise MigrationNotReady('Too many provider identities share a source key for bounded payload proof')
            if len(expected) + len(records) > 30:
                check()
                selectors, expected = [], {}
            selectors.append(json.loads(selector_json))
            expected.update(records)
        check()


class OwnerMigration:
    def __init__(self, key: state.PartitionKey, transport: PartitionTransport, *, firestore_client: Any = None):
        self.key = key
        self.transport = transport
        self.firestore_client = firestore_client

    def _route(self) -> state.Route:
        return state.get_route(self.key, firestore_client=self.firestore_client)

    @contextmanager
    def _copy_admission(self, token: str, ids: list[str], namespace: str, operation_kind: str) -> Iterator[None]:
        ticket = state.begin_mutation(
            self.key,
            affected_ids=ids,
            operation_kind=operation_kind,
            attempted_namespaces=[namespace],
            firestore_client=self.firestore_client,
        )
        if ticket.migration_token != token:
            state.finish_mutation(self.key, ticket, firestore_client=self.firestore_client)
            raise MigrationNotReady('Migration token is no longer active')
        # The durable pending ticket stops cutover/cancellation while a copy
        # request is in flight; the existing gate prevents post-delete writes.
        attempted = False
        try:
            with external_write_fence(self.key.uid, firestore_client=self.firestore_client):
                attempted = True
                yield
        except Exception:
            if attempted and ids != [BARRIER_ID]:
                state.mark_mutation_uncertain(self.key, ticket, firestore_client=self.firestore_client)
            else:
                state.finish_mutation(self.key, ticket, firestore_client=self.firestore_client)
            raise
        state.finish_mutation(self.key, ticket, firestore_client=self.firestore_client)

    def _write(self, token: str, path: str, namespace: str, scoped_ids: list[str], **payload: Any) -> int:
        with self._copy_admission(
            token, scoped_ids, namespace, 'copy_delete' if path == 'vectors/delete' else 'copy_upsert'
        ):
            return self.transport.write(path, namespace, **payload)

    def qualify(self, token: str, *, dimension: int, rollback: bool = False) -> dict:
        """Return evidence; caller explicitly commits it after user-path tests.

        A full owner reconciliation is intentionally used rather than assuming
        that the dirty journal enumerates every legacy-ID and filtered deletion.
        Active accounts can retry without exposing an incomplete target.
        """
        route = state.begin_migration(self.key, token, rollback=rollback, firestore_client=self.firestore_client)
        source, target = route.source_namespace, route.target_namespace
        if target is None:
            raise MigrationNotReady('Migration target is absent')
        probe = [1.0] + [0.0] * (dimension - 1)
        samples: list[list[float]] = []
        expected: dict[str, str] = {}
        groups: dict[str, dict[str, str]] = {}
        before = self._route()
        if before.pending_count or before.uncertain_count:
            raise MigrationNotReady('Source has unfinished mutations')
        # A no-op delete's LSN may never be indexed. This internal record has
        # no UID, so it cannot appear in any owner's search or copied inventory.
        source_barrier = self._write(token, 'vectors/upsert', source, [BARRIER_ID], vectors=[barrier_record(dimension)])
        self.transport.await_indexed(source, self.key.uid, probe, source_barrier)
        last_target_lsn = 0
        # Copy admission increments revisions itself; count those exact writes.
        owned_revision_increments = 2
        for records in self.transport.owned_pages(source, self.key.uid):
            if not records:
                continue
            for record in records:
                vector_id = record['id']
                if vector_id in expected:
                    raise MigrationNotReady('Source pagination changed while copying')
                expected[vector_id] = record_digest(record)
                metadata = record['metadata']
                fields = IDENTITY_FIELDS[self.key.family]
                if any(field not in metadata for field in fields):
                    raise MigrationNotReady('Record lacks an authoritative identity filter for payload proof')
                selector = json.dumps({field: {'$eq': metadata[field]} for field in fields}, sort_keys=True)
                groups.setdefault(selector, {})[vector_id] = expected[vector_id]
                if len(samples) < 3:
                    samples.append(record['values'])
            for batch in bounded_upsert_batches(records, target):
                last_target_lsn = self._write(token, 'vectors/upsert', target, [r['id'] for r in batch], vectors=batch)
                owned_revision_increments += 2
        # Remove target-only records, including records deleted during a prior
        # interrupted attempt. No namespace-wide deletion is ever used.
        for records in self.transport.owned_pages(target, self.key.uid):
            obsolete = [r['id'] for r in records if r['id'] not in expected]
            if obsolete:
                last_target_lsn = self._write(token, 'vectors/delete', target, obsolete, ids=obsolete)
                owned_revision_increments += 2
        last_target_lsn = self._write(
            token, 'vectors/upsert', target, [BARRIER_ID], vectors=[barrier_record(dimension)]
        )
        owned_revision_increments += 2
        target_indexed = self.transport.await_indexed(target, self.key.uid, probe, last_target_lsn)
        observed: dict[str, str] = {}
        for records in self.transport.owned_pages(target, self.key.uid):
            for record in records:
                if record['id'] in observed:
                    raise MigrationNotReady('Target pagination repeated a record')
                observed[record['id']] = record_digest(record)
        if expected != observed:
            raise MigrationNotReady('Copied IDs, values or metadata differ')
        source_ids = self.transport.fresh_inventory(source, self.key.uid, probe, source_barrier, groups)
        target_ids = self.transport.fresh_inventory(target, self.key.uid, probe, last_target_lsn, groups)
        if source_ids != set(expected) or target_ids != set(expected):
            raise MigrationNotReady('Fresh complete inventory differs from the copied snapshot')
        self.transport.verify_payloads(source, self.key.uid, probe, source_barrier, groups)
        self.transport.verify_payloads(target, self.key.uid, probe, last_target_lsn, groups)
        query_checks = []
        source_indexed = 0
        for vector in samples or [probe]:
            old, source_indexed = self.transport.query(source, self.key.uid, vector)
            new, target_indexed = self.transport.query(target, self.key.uid, vector)
            if source_indexed < source_barrier or target_indexed < last_target_lsn:
                raise MigrationNotReady('Query replica has not reached the verified write barrier')
            old_ids = [match['id'] for match in old['matches']]
            new_ids = [match['id'] for match in new['matches']]
            if old_ids != new_ids:
                raise MigrationNotReady('Search result order differs; preserve source route')
            query_checks.append({'matched': len(old_ids), 'passed': True})
        after = self._route()
        if (
            after.pending_count
            or after.uncertain_count
            or after.revision != before.revision + owned_revision_increments
        ):
            raise MigrationNotReady('Source changed during verification; reconcile again')
        return {
            'passed': True,
            'freshness_verified': True,
            'key_id': self.key.document_id,
            'migration_token': token,
            'revision': after.revision,
            'source_namespace': source,
            'target_namespace': target,
            'receipt_id': uuid4().hex,
            'source_barrier_lsn': source_barrier,
            'source_indexed_lsn': source_indexed,
            'target_write_lsn': last_target_lsn,
            'target_indexed_lsn': target_indexed,
            'records': len(expected),
            'query_checks': query_checks,
            'read_units': self.transport.read_units,
            'write_units': self.transport.write_units,
        }
