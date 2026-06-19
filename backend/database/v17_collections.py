from dataclasses import dataclass


@dataclass(frozen=True)
class V17Collections:
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
    def memory_lineage(self) -> str:
        return f"{self.user_root}/memory_lineage"

    @property
    def memory_evidence(self) -> str:
        return f"{self.user_root}/memory_evidence"

    @property
    def memory_runs(self) -> str:
        return f"{self.user_root}/memory_runs"

    @property
    def legacy_fallback(self) -> str:
        return f"{self.user_root}/memory_legacy_fallback"

    @property
    def memory_commits(self) -> str:
        return f"{self.user_root}/memory_commits"

    @property
    def memory_state_head(self) -> str:
        return f"{self.user_root}/memory_state/head"

    def all_collection_paths(self) -> list[str]:
        return [
            self.memory_items,
            self.memory_operations,
            self.memory_outbox,
            self.memory_lineage,
            self.memory_evidence,
            self.memory_runs,
            self.legacy_fallback,
            self.memory_commits,
        ]
