"""Canonical Firestore collection path helpers for memory storage (WS-G7).

Neutral ``MemoryCollections`` is the source of truth. Legacy ``MemoryCollections`` remains
an importable alias. Collection path strings are frozen — only Python symbol names change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCollections:
    uid: str

    @property
    def user_root(self) -> str:
        return f"users/{self.uid}"

    @property
    def memory_items(self) -> str:
        return f"{self.user_root}/memory_items"

    @property
    def memory_operations(self) -> str:
        return f"{self.user_root}/memory_operations"

    @property
    def memory_outbox(self) -> str:
        return f"{self.user_root}/memory_outbox"

    @property
    def memory_control_state(self) -> str:
        return f"{self.user_root}/memory_control/state"

    @property
    def memory_apply_control_state(self) -> str:
        return f"{self.user_root}/memory_state/apply_control"

    @property
    def memory_lineage(self) -> str:
        return f"{self.user_root}/memory_lineage"

    @property
    def memory_evidence(self) -> str:
        return f"{self.user_root}/memory_evidence"

    @property
    def memory_runs(self) -> str:
        return f"{self.user_root}/memory_runs"

    @property
    def memory_import_runs(self) -> str:
        return f"{self.user_root}/memory_import_runs"

    @property
    def memory_import_artifacts(self) -> str:
        return f"{self.user_root}/memory_import_artifacts"

    @property
    def memory_import_candidates(self) -> str:
        return f"{self.user_root}/memory_import_candidates"

    @property
    def non_active_memory_routes(self) -> str:
        return f"{self.user_root}/non_active_memory_routes"

    @property
    def short_term_lifecycle_transitions(self) -> str:
        return f"{self.user_root}/short_term_lifecycle_transitions"

    @property
    def legacy_fallback(self) -> str:
        return f"{self.user_root}/memory_legacy_fallback"

    @property
    def memory_commits(self) -> str:
        return f"{self.user_root}/memory_commits"

    @property
    def memory_state(self) -> str:
        return f"{self.user_root}/memory_state"

    @property
    def memory_state_head(self) -> str:
        return f"{self.user_root}/memory_state/head"

    @property
    def v3_compatibility_projection_state(self) -> str:
        return f"{self.user_root}/v3_compatibility_projection/state"

    @property
    def v3_compatibility_projection_items(self) -> str:
        return f"{self.user_root}/v3_compatibility_projection_items"

    def all_collection_paths(self) -> list[str]:
        return [
            self.memory_items,
            self.memory_operations,
            self.memory_outbox,
            self.memory_lineage,
            self.memory_evidence,
            self.memory_runs,
            self.memory_import_runs,
            self.memory_import_artifacts,
            self.memory_import_candidates,
            self.non_active_memory_routes,
            self.short_term_lifecycle_transitions,
            self.legacy_fallback,
            self.memory_commits,
            self.memory_state,
            self.v3_compatibility_projection_items,
        ]


MemoryCollections = MemoryCollections

__all__ = ["MemoryCollections", "MemoryCollections"]
