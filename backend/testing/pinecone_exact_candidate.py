"""Dev-only exact retrieval experiment, never imported by a serving entrypoint.

Completeness comes from a synthetic fixture that owns every write, NOT from
ANN results, a terminal metadata page, or a query LSN. Production enrollment
and snapshot renewal after writes are deliberately not implemented.
"""

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Callable

from database.pinecone_partition_migration import record_digest
from database.pinecone_partition_state import PartitionKey


class CandidateRejected(ValueError):
    """The experiment cannot establish the requested exact result."""


@dataclass(frozen=True)
class ReadAuthority:
    index_name: str
    uid: str
    namespace: str
    revision: int
    migration_token: str | None = None
    pending_count: int = 0
    uncertain_count: int = 0
    route_exists: bool = True
    deletion_blocked: bool = False


def _unit(values: Any, dimension: int) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) != dimension:
        raise CandidateRejected('Wrong vector dimension')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise CandidateRejected('Invalid vector coordinate')
    scale = max(abs(v) for v in values)
    if not scale:
        raise CandidateRejected('Zero vector has no cosine similarity')
    scaled = tuple(v / scale for v in values)
    norm = math.sqrt(math.fsum(v * v for v in scaled))
    return tuple(v / norm for v in scaled)


class ExactFixtureOwnerIndex:
    """Immutable, bounded fixture snapshot through the existing query interface.

    The caller supplies both its authoritative complete write manifest and fetched
    provider records. Matching those proves this isolated fixture, not arbitrary
    production owners. A namespace-specific write/query LSN is an extra gate.
    No fallback or persistence: a write invalidates this instance permanently.
    """

    def __init__(
        self,
        *,
        authority: ReadAuthority,
        read_authority: Callable[[], ReadAuthority],
        manifest: list[dict],
        fetched: list[dict],
        provider_namespace: str,
        write_lsn: int,
        indexed_lsn: int,
        dimension: int = 3072,
    ):
        if authority.index_name != 'memories-backend-dev' or not authority.uid.startswith('exact-candidate-'):
            raise CandidateRejected('Only isolated development fixtures are admitted')
        key = PartitionKey(authority.index_name, 'ns4', authority.uid)
        if authority.namespace not in {key.family, key.partition_namespace}:
            raise CandidateRejected('Namespace is not this owner’s ns4 source or partition')
        if type(dimension) is not int or not 1 <= dimension <= 3072:
            raise CandidateRejected('Dimension is outside the experiment bound')
        if type(authority.revision) is not int or authority.revision < 0:
            raise CandidateRejected('Invalid route generation')
        if not authority.namespace or provider_namespace != authority.namespace:
            raise CandidateRejected('Provider freshness belongs to another namespace')
        if type(write_lsn) is not int or type(indexed_lsn) is not int or not 0 < write_lsn <= indexed_lsn:
            raise CandidateRejected('Missing or stale provider freshness')
        if len(manifest) > 128 or len(fetched) > 128:
            raise CandidateRejected('Fixture exceeds bounded exact-search capacity')
        self.authority = authority
        self.read_authority = read_authority
        self.dimension = dimension
        self._guard()
        expected = self._inventory(manifest)
        actual = self._inventory(fetched)
        if expected != actual:
            raise CandidateRejected('Provider records differ from the complete fixture manifest')
        self._records = tuple(
            (row['id'], _unit(row['values'], dimension), deepcopy(row['metadata']), tuple(row['values']))
            for row in sorted(fetched, key=lambda r: r['id'])
        )
        self._guard()

    def _inventory(self, rows: list[dict]) -> dict[str, str]:
        found = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
                raise CandidateRejected('Missing vector identity')
            metadata = row.get('metadata')
            if not isinstance(metadata, dict) or metadata.get('uid') != self.authority.uid:
                raise CandidateRejected('Foreign or missing owner')
            if not isinstance(metadata.get('action_item_id'), str) or not metadata['action_item_id']:
                raise CandidateRejected('Missing action-item identity')
            if row['id'] in found:
                raise CandidateRejected('Duplicate record identity')
            _unit(row.get('values'), self.dimension)
            found[row['id']] = record_digest(row)
        return found

    def _guard(self) -> None:
        actual = self.read_authority()
        if (
            actual != self.authority
            or not actual.route_exists
            or actual.deletion_blocked
            or actual.pending_count
            or actual.uncertain_count
        ):
            raise CandidateRejected('Fixture authority changed or is unsafe')

    def query(
        self,
        *,
        namespace: str,
        vector: list[float],
        top_k: int,
        filter: dict,
        include_metadata: bool = False,
        include_values: bool = False,
        **unsupported: Any,
    ) -> dict:
        if namespace != 'ns4' or unsupported:
            raise CandidateRejected('Only the ns4 dense-vector query is qualified')
        if filter not in ({'uid': self.authority.uid}, {'uid': {'$eq': self.authority.uid}}):
            raise CandidateRejected('Only the exact authenticated-owner filter is qualified')
        if type(top_k) is not int or not 1 <= top_k <= 128:
            raise CandidateRejected('Invalid bounded top_k')
        if type(include_metadata) is not bool or type(include_values) is not bool:
            raise CandidateRejected('Invalid result projection')
        query = _unit(vector, self.dimension)
        self._guard()
        matches = []
        for vector_id, unit, metadata, values in self._records:
            score = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(query, unit))))
            row = {'id': vector_id, 'score': score}
            if include_metadata:
                row['metadata'] = deepcopy(metadata)
            if include_values:
                row['values'] = list(values)
            matches.append(row)
        matches.sort(key=lambda m: (-m['score'], m['id']))
        self._guard()
        return {'matches': matches[:top_k], 'namespace': self.authority.namespace}
