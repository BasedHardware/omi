from __future__ import annotations

"""Canonical non active route audit module (WS-G8a).

Canonical non-active route audit helpers for admin reports and benchmarks.
"""


from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from database._client import db
from database.memory_collections import MemoryCollections
from database.memory_non_active_routes import NonActiveRoute, PersistedNonActiveRouteOutcome


def _empty_audit_evidence() -> List["NonActiveRouteAuditEvidence"]:
    return []


class NonActiveRouteAuditEvidence(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    uid: str
    outcome_id: str
    route: NonActiveRoute
    source_ids: List[str]
    terminal_outcome: str
    run_id: str
    patch_id: Optional[str] = None
    created_at: datetime
    remediation_state: str
    preserved: bool
    observable_loss: bool
    accounted: bool = True
    default_long_term_visible: bool = False


class NonActiveRouteAuditReport(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    uid: str
    status: str
    total_accounted_outcomes: int
    counts_by_route: Dict[str, int]
    evidence: List[NonActiveRouteAuditEvidence] = Field(default_factory=_empty_audit_evidence)
    missing_source_ids: List[str] = Field(default_factory=list)
    red_reasons: List[str] = Field(default_factory=list)


def build_non_active_route_audit_report(
    uid: str,
    route_docs: Iterable[PersistedNonActiveRouteOutcome | Dict[str, Any]],
    *,
    expected_source_ids: Optional[Iterable[str]] = None,
) -> NonActiveRouteAuditReport:
    """Summarize non-active route-store docs for no-silent-data-loss/benchmark audits.

    This helper intentionally consumes already-fetched route-store documents rather than
    querying Firestore directly, so it can be reused by admin reports, offline benchmark
    harnesses, and unit tests without changing the default Long-term read path.
    """

    counts_by_route = {route.value: 0 for route in NonActiveRoute}
    evidence: List[NonActiveRouteAuditEvidence] = []
    red_reasons: List[str] = []
    source_terminal_counts: Dict[str, int] = {}
    observed_sources: Set[str] = set()

    for raw_doc in route_docs:
        outcome = _coerce_route_doc(raw_doc)
        counts_by_route[outcome.route.value] += 1

        if outcome.uid != uid:
            red_reasons.append(f"route {outcome.outcome_id} belongs to uid {outcome.uid}, expected {uid}")

        if outcome.default_long_term_visible:
            red_reasons.append(f"non-active route {outcome.outcome_id} is default Long-term visible")

        for source_id in outcome.source_ids:
            observed_sources.add(source_id)
            source_terminal_counts[source_id] = source_terminal_counts.get(source_id, 0) + 1

        evidence.append(
            NonActiveRouteAuditEvidence(
                uid=outcome.uid,
                outcome_id=outcome.outcome_id,
                route=outcome.route,
                source_ids=outcome.source_ids,
                terminal_outcome=f"non_active_route:{outcome.route.value}",
                run_id=outcome.run_id,
                patch_id=outcome.patch_id,
                created_at=outcome.created_at,
                remediation_state=_remediation_state(outcome),
                preserved=_preserved(outcome),
                observable_loss=_observable_loss(outcome),
                accounted=True,
                default_long_term_visible=outcome.default_long_term_visible,
            )
        )

    duplicate_sources = sorted(source_id for source_id, count in source_terminal_counts.items() if count > 1)
    for source_id in duplicate_sources:
        red_reasons.append(f"duplicate terminal outcomes for source {source_id}")

    missing_source_ids: List[str] = []
    if expected_source_ids is not None:
        expected = sorted({source_id for source_id in expected_source_ids if source_id})
        missing_source_ids = [source_id for source_id in expected if source_id not in observed_sources]
        for source_id in missing_source_ids:
            red_reasons.append(f"missing terminal outcome for source {source_id}")

    return NonActiveRouteAuditReport(
        uid=uid,
        status="red" if red_reasons else "green",
        total_accounted_outcomes=len(evidence),
        counts_by_route=counts_by_route,
        evidence=sorted(evidence, key=lambda item: (item.route.value, item.outcome_id)),
        missing_source_ids=missing_source_ids,
        red_reasons=red_reasons,
    )


def _coerce_route_doc(raw_doc: PersistedNonActiveRouteOutcome | Dict[str, Any]) -> PersistedNonActiveRouteOutcome:
    if isinstance(raw_doc, PersistedNonActiveRouteOutcome):
        return raw_doc
    return PersistedNonActiveRouteOutcome(**raw_doc)


def _remediation_state(outcome: PersistedNonActiveRouteOutcome) -> str:
    value = outcome.audit_metadata.get("remediation_state")
    if isinstance(value, str) and value.strip():
        return value
    return "accounted_terminal_outcome"


def _preserved(outcome: PersistedNonActiveRouteOutcome) -> bool:
    value = outcome.audit_metadata.get("preserved")
    if isinstance(value, bool):
        return value
    return outcome.route in {
        NonActiveRoute.review,
        NonActiveRoute.archive,
        NonActiveRoute.context_only,
        NonActiveRoute.hidden,
    }


def _observable_loss(outcome: PersistedNonActiveRouteOutcome) -> bool:
    value = outcome.audit_metadata.get("observable_loss")
    if isinstance(value, bool):
        return value
    return outcome.route in {NonActiveRoute.reject, NonActiveRoute.skip}


def fetch_non_active_route_audit_report(
    uid: str,
    *,
    run_id: Optional[str] = None,
    expected_source_ids: Optional[Iterable[str]] = None,
    db_client: Any = db,
) -> NonActiveRouteAuditReport:
    """Fetch route-store docs and build the memory non-active no-silent-loss audit report."""

    route_docs = _fetch_non_active_route_docs(uid, run_id=run_id, db_client=db_client)
    return build_non_active_route_audit_report(uid, route_docs, expected_source_ids=expected_source_ids)


def _fetch_non_active_route_docs(uid: str, *, run_id: Optional[str], db_client: Any) -> List[Dict[str, Any]]:
    collection_path = MemoryCollections(uid=uid).non_active_memory_routes
    query = db_client.collection(collection_path)
    if run_id:
        query = query.where("run_id", "==", run_id)
    return [snapshot.to_dict() or {} for snapshot in query.stream()]
