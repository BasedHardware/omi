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
    def memory_deletion_receipts(self) -> str:
        """Content-free, 30-day anti-resurrection receipts."""
        return f"{self.user_root}/memory_deletion_receipts"

    @property
    def memory_source_replacements(self) -> str:
        return f"{self.user_root}/memory_source_replacements"

    @property
    def memory_ledger_reopens(self) -> str:
        """Immutable source-to-tail receipts for standalone ledger reopening."""
        return f"{self.user_root}/memory_ledger_reopens"

    @property
    def jit_trigger_feedback(self) -> str:
        """Content-free idempotency receipts for explicit trigger feedback."""
        return f"{self.user_root}/jit_trigger_feedback"

    @property
    def jit_proactivity_events(self) -> str:
        return f"{self.user_root}/jit_proactivity_events"

    @property
    def jit_proactivity_daily_budgets(self) -> str:
        return f"{self.user_root}/jit_proactivity_daily_budgets"

    @property
    def jit_proactivity_candidate_turns(self) -> str:
        return f"{self.user_root}/jit_proactivity_candidate_turns"

    @property
    def memory_outbox(self) -> str:
        return f"{self.user_root}/memory_outbox"

    @property
    def memory_control_state(self) -> str:
        return f"{self.user_root}/memory_control/state"

    @property
    def legacy_canonical_backfill_checkpoint(self) -> str:
        return f"{self.user_root}/memory_control/legacy_canonical_backfill"

    @property
    def knowledge_ledger_migration_state(self) -> str:
        """Per-user cutover proof; never a second memory authority."""
        return f"{self.user_root}/memory_control/knowledge_ledger_migration"

    @property
    def knowledge_ledger_prompt_projection(self) -> str:
        """Bounded prompt receipt produced by the canonical migration sweep."""
        return f"{self.user_root}/memory_control/knowledge_ledger_prompt_projection"

    @property
    def knowledge_ledger_writer_transition_receipt(self) -> str:
        """Content-free proof for the latest writer-mode transition."""
        return f"{self.user_root}/memory_control/knowledge_ledger_writer_transition_receipt"

    @property
    def historical_graph_enrichment_cursor(self) -> str:
        return f"{self.user_root}/memory_control/historical_graph_enrichment"

    @property
    def memory_apply_control_state(self) -> str:
        return f"{self.user_root}/memory_state/apply_control"

    @property
    def memory_lineage(self) -> str:
        return f"{self.user_root}/memory_lineage"

    @property
    def memory_historical_overrides(self) -> str:
        """Canonical suppression records for legacy public memory identities."""
        return f"{self.user_root}/memory_historical_overrides"

    @property
    def memory_evidence(self) -> str:
        return f"{self.user_root}/memory_evidence"

    @property
    def memory_graph_assertions(self) -> str:
        return f"{self.user_root}/memory_graph_assertions"

    @property
    def memory_review_queue(self) -> str:
        return f"{self.user_root}/memory_review_queue"

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
    def daily_memory_sweep_receipts(self) -> str:
        """Content-free per-source receipts for the dark daily memory sweep."""
        return f"{self.user_root}/daily_memory_sweep_receipts"

    @property
    def daily_memory_sweep_sources(self) -> str:
        """Backend-produced, deletion-scoped daily sweep staging packets."""
        return f"{self.user_root}/daily_memory_sweep_sources"

    @property
    def daily_memory_sweep_onboarding_sources(self) -> str:
        return f"{self.user_root}/daily_memory_sweep_onboarding_sources"

    @property
    def daily_memory_sweep_daily_summary_staged(self) -> str:
        return f"{self.user_root}/daily_memory_sweep_daily_summary_staged"

    @property
    def daily_memory_sweep_onboarding_staged(self) -> str:
        return f"{self.user_root}/daily_memory_sweep_onboarding_staged"

    @property
    def daily_memory_sweep_model_invocations(self) -> str:
        return f"{self.user_root}/daily_memory_sweep_model_invocations"

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

    def all_collection_paths(self) -> list[str]:
        return [
            self.memory_items,
            self.memory_operations,
            self.memory_deletion_receipts,
            self.memory_source_replacements,
            self.memory_ledger_reopens,
            self.jit_trigger_feedback,
            self.jit_proactivity_events,
            self.jit_proactivity_daily_budgets,
            self.jit_proactivity_candidate_turns,
            self.memory_outbox,
            self.memory_lineage,
            self.memory_historical_overrides,
            self.memory_evidence,
            self.memory_graph_assertions,
            self.memory_review_queue,
            self.memory_runs,
            self.memory_import_runs,
            self.memory_import_artifacts,
            self.memory_import_candidates,
            self.daily_memory_sweep_receipts,
            self.daily_memory_sweep_sources,
            self.daily_memory_sweep_onboarding_sources,
            self.daily_memory_sweep_daily_summary_staged,
            self.daily_memory_sweep_onboarding_staged,
            self.daily_memory_sweep_model_invocations,
            self.non_active_memory_routes,
            self.short_term_lifecycle_transitions,
            self.legacy_fallback,
            self.memory_commits,
            self.memory_state,
        ]


MemoryCollections = MemoryCollections

__all__ = ["MemoryCollections", "MemoryCollections"]
