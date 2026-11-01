"""Prepared phase-two adapter. No reads, writes, provider calls or execution on import."""

from __future__ import annotations

import copy
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from evals.dream_verifier.contracts import Snapshot, digest, project
from evals.dream_verifier.gateway import require_replay_pod


@dataclass(frozen=True)
class OwnerProposal:
    owner_uid: str
    staged: Any
    gold: str
    reason_category: str


def owner_items(rows: Iterable[OwnerProposal], *, approved_owner_uid: str) -> Iterator[dict[str, Any]]:
    """Consume the coordinator's owner-scoped in-pod loader entirely in memory.

    This adapter intentionally has no account discovery or Firestore query.
    The loader must enforce actual owner scope before constructing envelopes;
    declared UID equality is a second guard, not proof of the loader's query.
    Labels must already be adjudicated in-pod; no generated real-data labels.
    """
    require_replay_pod()
    if not approved_owner_uid or os.getenv('DREAM_VERIFIER_APPROVED_OWNER_UID') != approved_owner_uid:
        raise ValueError('approved_owner_scope_required')
    for envelope in rows:
        if envelope.owner_uid != approved_owner_uid or envelope.gold not in {'accept', 'reject'}:
            raise ValueError('owner_scope_or_adjudicated_label_mismatch')
        staged = envelope.staged
        operation = staged.operation.model_dump(mode='json')
        # Opaque eval IDs avoid emitting account refs in aggregate reports.
        identifier = digest({'owner': approved_owner_uid, 'proposal': staged.id})[:28]
        snapshot = Snapshot(identifier, staged.kind, operation, tuple(staged.refs), copy.deepcopy(staged.records))
        verifier_input = project(snapshot)
        yield {
            'id': identifier,
            'stratum': staged.kind,
            'staged': {
                'kind': staged.kind,
                'operation': operation,
                'refs': list(staged.refs),
                'records': snapshot.records,
            },
            'verifier_input': verifier_input,
            'evidence_sha256': digest(verifier_input),
            'gold': envelope.gold,
            'reason_category': envelope.reason_category,
        }
