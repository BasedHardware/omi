from __future__ import annotations

import pytest

from modal import memory_maintenance_job


def test_historical_graph_enrichment_is_disabled_without_an_explicit_target(monkeypatch):
    monkeypatch.delenv(memory_maintenance_job.HISTORICAL_GRAPH_ENRICHMENT_UID, raising=False)

    assert memory_maintenance_job._historical_graph_enrichment_from_env() is None


def test_historical_graph_enrichment_requires_an_explicit_firestore_project(monkeypatch):
    monkeypatch.setenv(memory_maintenance_job.HISTORICAL_GRAPH_ENRICHMENT_UID, "u1")
    monkeypatch.delenv("HISTORICAL_GRAPH_ENRICHMENT_FIRESTORE_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="explicit Firestore project"):
        memory_maintenance_job._historical_graph_enrichment_from_env()
