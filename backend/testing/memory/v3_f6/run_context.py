"""Run context contracts for memory-V3-F6 read-only evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    project_id: str
    principal: str
