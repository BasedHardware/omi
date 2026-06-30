import asyncio
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from utils.memory_ingestion import export_runner
from utils.memory_ingestion.models import (
    ActorDescriptor,
    ExistingMemorySnapshot,
    MemoryPipelineConfig,
    MemoryPipelineInput,
    OutputConfig,
    RawContextEvent,
    RoutingConfig,
    SourceDescriptor,
    SourceRef,
    UserStateSnapshot,
)
from utils.memory_ingestion.pipeline import CoreMemoryPipeline


def _input(*, text=None, payload=None, user_state=None, config=None, run_id="run-1", mode="offline"):
    return MemoryPipelineInput(
        run_id=run_id,
        mode=mode,
        source=SourceDescriptor(source_type="benchmark_fixture", source_id="fixture-1"),
        actor=ActorDescriptor(synthetic_user_id="synthetic-user", display_name="User"),
        user_state=user_state
        or UserStateSnapshot(snapshot_id="snapshot-1", snapshot_at=datetime(2026, 6, 8, tzinfo=timezone.utc)),
        raw_events=[
            RawContextEvent(
                event_id="event-1",
                event_type="manual_text",
                text=text,
                structured_payload=payload or {},
                source_ref=SourceRef(fixture_id="fixture-1"),
            )
        ],
        config=config or MemoryPipelineConfig(),
    )


def _run(pipeline_input, **kwargs):
    return asyncio.run(CoreMemoryPipeline(**kwargs).run(pipeline_input))


def _frame_payload(text="User prefers headless tools."):
    return {
        "frame_type": "preference",
        "predicate": "prefers",
        "object": {"object_type": "literal", "value": "headless tools"},
        "canonical_text": text,
        "confidence": "high",
        "durability": "medium_term",
        "scope": "global",
        "importance": "high",
    }


def test_core_models_reject_benchmark_labels():
    data = _input(text="I like espresso.").model_dump(mode="json")
    data["labels"] = {"should_not": "enter core"}
    with pytest.raises(ValidationError):
        MemoryPipelineInput.model_validate(data)


def test_structured_frames_create_memory_and_vector_plan():
    pipeline_input = _input(payload={"memory_frames": [_frame_payload()]})
    output = _run(pipeline_input)

    assert output.status == "ok"
    assert len(output.event_frames) == 1
    assert output.event_frames[0].scope == "global"
    assert output.event_frames[0].importance == "high"
    assert [decision.action for decision in output.decisions] == ["create_memory"]
    assert len(output.mutation_plan.creates) == 1
    assert len(output.vector_plan.upserts) == 1
    assert output.vector_plan.upserts[0].source_id == output.mutation_plan.creates[0].memory_id


def test_review_uncertain_routing_profile_routes_uncertain_frames_to_review():
    payload = {"memory_frames": [_frame_payload() | {"uncertainty_reasons": ["inferred_not_stated"]}]}
    config = MemoryPipelineConfig(routing=RoutingConfig(review_uncertain=True))

    output = _run(_input(payload=payload, config=config))

    assert [decision.action for decision in output.decisions] == ["route_to_review"]
    assert output.mutation_plan.creates == []
    assert output.vector_plan.upserts == []
    assert len(output.review_items) == 1


def test_fingerprint_and_ids_are_stable_across_offline_shadow_backfill_modes():
    base = _input(payload={"memory_frames": [_frame_payload()]}, mode="offline", run_id="run-a")
    shadow = _input(payload={"memory_frames": [_frame_payload()]}, mode="shadow", run_id="run-b")
    backfill = _input(payload={"memory_frames": [_frame_payload()]}, mode="backfill", run_id="run-c")

    offline_output = _run(base)
    shadow_output = _run(shadow)
    backfill_output = _run(backfill)

    assert offline_output.input_fingerprint == shadow_output.input_fingerprint == backfill_output.input_fingerprint
    assert offline_output.event_frames[0].frame_id == shadow_output.event_frames[0].frame_id
    assert shadow_output.event_frames[0].frame_id == backfill_output.event_frames[0].frame_id
    assert offline_output.decisions[0].decision_id == shadow_output.decisions[0].decision_id


def test_hard_secret_event_is_dropped_before_model_extraction_but_emits_rejection_signal():
    pipeline_input = _input(
        text="Remember that my API key is sk-1234567890abcdefghijklmnop",
        payload={"nested": {"token": "token=abcdefghijklmnopqrstuvwxyz123456"}},
        config=MemoryPipelineConfig(output=OutputConfig(include_private_input_fingerprint=True)),
    )
    output = _run(pipeline_input, private_fingerprint_key="test-key")
    dumped = output.model_dump_json()

    assert output.private_input_fingerprint.startswith("pifp_")
    assert output.stats.redaction_count == 2
    assert output.stats.dropped_artifact_count == 1
    assert len(output.event_frames) == 2
    assert output.mutation_plan.creates == []
    assert output.vector_plan.upserts == []
    assert output.audit.dropped_artifacts[0].artifact_dropped is True
    assert output.audit.dropped_artifacts[0].reason == "secret"
    assert output.audit.dropped_artifacts[0].categories == ["api_key", "token"]
    assert "client_secret_scrub_miss: 1 artifact(s) dropped by backend" in output.audit.stage_traces[0].notes
    assert "sk-1234567890abcdefghijklmnop" not in dumped
    assert "abcdefghijklmnopqrstuvwxyz123456" not in dumped
    assert "[REDACTED_API_KEY]" in dumped
    assert "reject_secret" in {decision.action for decision in output.decisions}
    assert "secret_or_credential" in {item.reason for item in output.rejected_items}


def test_email_pii_is_not_whole_dropped_by_secret_gate():
    output = _run(
        _input(
            text="Please reach me at user@example.com regarding the Atlas project invoice.",
            payload={"memory_frames": [_frame_payload()]},
        )
    )

    assert output.stats.redaction_count == 0
    assert output.stats.dropped_artifact_count == 0
    assert len(output.event_frames) == 1
    assert len(output.mutation_plan.creates) == 1


def test_rejected_memory_prevents_recreation():
    state = UserStateSnapshot(
        snapshot_id="snapshot-1",
        snapshot_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        rejected_memories=[
            ExistingMemorySnapshot(
                memory_id="mem-rejected",
                text="User prefers headless tools.",
                status="rejected",
                rejected=True,
            )
        ],
    )
    output = _run(_input(payload={"memory_frames": [_frame_payload()]}, user_state=state))

    assert [decision.action for decision in output.decisions] == ["reject_matches_rejected"]
    assert output.mutation_plan.creates == []
    assert output.vector_plan.upserts == []


def test_locked_or_reviewed_active_memory_routes_to_review():
    state = UserStateSnapshot(
        snapshot_id="snapshot-1",
        snapshot_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        active_memories=[
            ExistingMemorySnapshot(
                memory_id="mem-locked",
                text="User prefers headless tools.",
                locked=True,
                reviewed=True,
            )
        ],
    )
    output = _run(_input(payload={"memory_frames": [_frame_payload()]}, user_state=state))

    assert [decision.action for decision in output.decisions] == ["route_to_review"]
    assert output.mutation_plan.creates == []
    assert len(output.review_items) == 1
    assert output.review_items[0].reason == "conflicts_with_locked_memory"


def test_negated_change_supersedes_active_memory_with_vector_delete():
    state = UserStateSnapshot(
        snapshot_id="snapshot-1",
        snapshot_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        active_memories=[
            ExistingMemorySnapshot(
                memory_id="mem-old",
                text="User prefers headless tools.",
                kind="preference",
            )
        ],
    )
    payload = {
        "memory_frames": [
            {
                "frame_type": "preference",
                "predicate": "no_longer_prefers",
                "object": {"object_type": "literal", "value": "headless tools"},
                "canonical_text": "User no longer prefers headless tools.",
                "confidence": "high",
                "durability": "medium_term",
                "modality": {"kind": "negated"},
                "scope": "global",
                "importance": "high",
            }
        ]
    }

    output = _run(_input(payload=payload, user_state=state))

    assert [decision.action for decision in output.decisions] == ["supersede_memory"]
    assert len(output.mutation_plan.creates) == 1
    assert len(output.mutation_plan.invalidations) == 1
    assert output.mutation_plan.invalidations[0].memory_id == "mem-old"
    assert output.mutation_plan.invalidations[0].superseded_by_memory_id == output.mutation_plan.creates[0].memory_id
    assert len(output.vector_plan.upserts) == 1
    assert len(output.vector_plan.deletes) == 1
    assert output.vector_plan.deletes[0].source_id == "mem-old"


def test_task_candidates_route_to_task_not_memory():
    payload = {
        "memory_frames": [
            {
                "frame_type": "task_candidate",
                "predicate": "needs",
                "object": {"object_type": "literal", "value": "send the launch note"},
                "canonical_text": "User needs to send the launch note.",
                "confidence": "high",
                "durability": "short_term",
                "scope": "conversation",
                "importance": "medium",
            }
        ]
    }
    output = _run(_input(payload=payload))

    assert [decision.action for decision in output.decisions] == ["route_to_task"]
    assert output.mutation_plan.creates == []
    assert len(output.mutation_plan.task_routes) == 1


def test_export_runner_refuses_resume_with_mismatched_config():
    config = {"schema_version": "memory_export_run_config.v1", "typed": True, "routing_profile": "default"}
    manifest = {"shards": {"run-1": {"status": "ok"}}, "run_config_fingerprint": export_runner._fingerprint(config)}

    with pytest.raises(RuntimeError, match="config does not match"):
        export_runner._assert_resume_config_compatible(
            manifest,
            {"schema_version": "memory_export_run_config.v1", "typed": True, "routing_profile": "shadow-safe"},
            allow_legacy_resume=False,
        )


def test_cli_reads_json_and_writes_pipeline_output(tmp_path):
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    input_path.write_text(_input(payload={"memory_frames": [_frame_payload()]}).model_dump_json())

    subprocess.run(
        [
            sys.executable,
            "-m",
            "utils.memory_ingestion.cli",
            "run",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
    )
    output = json.loads(output_path.read_text())
    assert output["schema_version"] == "memory_pipeline_output"
    assert output["decisions"][0]["action"] == "create_memory"


# ---------------------------------------------------------------------------
# Signal density filter tests (T-H10 / committee-D2)
# ---------------------------------------------------------------------------


def test_signal_density_rejects_pure_chitchat():
    """Gold=0 noise examples like 'Thanks, sounds good.' must be rejected early."""
    output = _run(_input(text="Thanks, sounds good."))
    assert output.status == "failed"
    assert any("signal density" in err.message for err in output.errors)
    assert len(output.event_frames) == 0
    assert len(output.mutation_plan.creates) == 0


def test_signal_density_rejects_weather_chitchat():
    """'The weather is nice today.' — no memory signal."""
    output = _run(_input(text="The weather is nice today."))
    assert output.status == "failed"
    assert any("signal density" in err.message for err in output.errors)


def test_signal_density_rejects_empty_chatter():
    """'Pure chatter/no-memory example.' — explicit noise marker."""
    output = _run(_input(text="Pure chatter/no-memory example."))
    assert output.status == "failed"
    assert any("signal density" in err.message for err in output.errors)


def test_signal_density_accepts_substantive_text():
    """Normal memory-bearing input must pass through."""
    output = _run(_input(text="I prefer oat milk in my coffee every morning."))
    assert output.status != "failed"
    # Should not have a signal-density error
    assert not any("signal density" in err.message for err in output.errors)


def test_signal_density_accepts_structured_payload_without_text():
    """Events with structured payload but no text should not be penalized."""
    output = _run(_input(text=None, payload={"memory_frames": [_frame_payload()]}))
    assert output.status == "ok"
    assert len(output.event_frames) == 1


def test_signal_density_filler_heavy_transcript_is_rejected():
    """A turn that is mostly fillers: 'Um, like, uh, you know, yeah, ok.'"""
    output = _run(_input(text="Um, like, uh, you know, yeah, ok, I mean, right?"))
    assert output.status == "failed"
    assert any("signal density" in err.message for err in output.errors)


def test_signal_density_multi_event_average():
    """Multiple events where average density is below threshold."""
    pipeline_input = MemoryPipelineInput(
        run_id="run-multi",
        mode="offline",
        source=SourceDescriptor(source_type="benchmark_fixture", source_id="fixture-1"),
        actor=ActorDescriptor(synthetic_user_id="synthetic-user", display_name="User"),
        user_state=UserStateSnapshot(
            snapshot_id="snapshot-1",
            snapshot_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
        raw_events=[
            RawContextEvent(
                event_id="e1",
                event_type="manual_text",
                text="Uh huh.",
                source_ref=SourceRef(fixture_id="f1"),
            ),
            RawContextEvent(
                event_id="e2",
                event_type="manual_text",
                text="Yeah, ok.",
                source_ref=SourceRef(fixture_id="f1"),
            ),
            RawContextEvent(
                event_id="e3",
                event_type="manual_text",
                text="Sure thing.",
                source_ref=SourceRef(fixture_id="f1"),
            ),
        ],
        config=MemoryPipelineConfig(),
    )
    output = _run(pipeline_input)
    assert output.status == "failed"
    assert any("signal density" in err.message for err in output.errors)


def test_compute_signal_density_unit():
    """Direct unit test of the helper function."""
    from utils.memory_ingestion.pipeline import _compute_signal_density, _MIN_SIGNAL_DENSITY

    # Substantial text
    substantial = _input(text="I work on Atlas project using Python and Postgres.")
    assert _compute_signal_density(substantial) >= _MIN_SIGNAL_DENSITY

    # Pure filler
    filler = _input(text="um like yeah you know uh ok")
    assert _compute_signal_density(filler) < _MIN_SIGNAL_DENSITY

    # No text events
    no_text = _input(text=None, payload={"key": "val"})
    assert _compute_signal_density(no_text) == 0.0
