from __future__ import annotations

from utils.memory_ingestion.models import AppliedMemoryPipelineOutput, MemoryPipelineOutput, PipelineError


class NoopMemoryPipelineApplier:
    async def apply(self, uid: str, output: MemoryPipelineOutput) -> AppliedMemoryPipelineOutput:
        if output.status != "ok":
            return AppliedMemoryPipelineOutput(
                run_id=output.run_id,
                status="failed",
                errors=[
                    PipelineError(
                        error_id=f"apply_blocked_{output.run_id}",
                        stage_name="noop_apply",
                        severity="error",
                        code="output_not_ok",
                        message="Noop applier only accepts ok outputs.",
                    )
                ],
            )
        mutation_ids = []
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.creates)
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.updates)
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.invalidations)
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.evidence_links)
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.review_upserts)
        mutation_ids.extend(mutation.mutation_id for mutation in output.mutation_plan.task_routes)
        return AppliedMemoryPipelineOutput(run_id=output.run_id, status="ok", applied_mutation_ids=mutation_ids)
