from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from utils.memory_ingestion.adapters.production_like_model import ProductionLikeMemoryModelClient
from utils.memory_ingestion.models import (
    ActorDescriptor,
    ExistingMemorySnapshot,
    MemoryPipelineConfig,
    MemoryPipelineInput,
    ModelConfig,
    RoutingConfig,
    RawContextEvent,
    SourceDescriptor,
    SourceRef,
    UserStateSnapshot,
)
from utils.memory_ingestion.pipeline import CoreMemoryPipeline

DEFAULT_EXPORT_ROOT = "omi-export-bigbeeme33-30day-20260608-1611/"


@dataclass
class ExportDataset:
    segments: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    sessions: list[dict[str, Any]]


async def run_export(args: argparse.Namespace) -> None:
    _load_env_file(args.env_file)
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --model-client production-like")

    run_dir = Path(args.run_dir)
    input_dir = run_dir / "inputs"
    output_dir = run_dir / "outputs"
    run_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    dataset = _read_export(args.export_zip, args.export_root)
    user_state = _build_user_state(dataset.memories, args.memory_snapshot_limit)
    sessions = _group_segments_by_session(dataset.segments)
    if args.session_id:
        sessions = {args.session_id: sessions[args.session_id]} if args.session_id in sessions else {}

    session_items = sorted(
        sessions.items(),
        key=lambda item: (
            _event_sort_key(item[1][0]) if item[1] else (0.0, 0, item[0]),
            item[0],
        ),
    )
    if args.limit:
        session_items = session_items[: args.limit]

    run_config = _run_config(args)
    manifest = _load_manifest(run_dir)
    _assert_resume_config_compatible(manifest, run_config, args.allow_legacy_resume)
    manifest.update(
        {
            "schema_version": "memory_export_run_manifest.v1",
            "run_config": run_config,
            "run_config_fingerprint": _fingerprint(run_config),
            "export_zip": str(Path(args.export_zip).resolve()),
            "run_dir": str(run_dir.resolve()),
            "started_at": manifest.get("started_at") or _now_iso(),
            "updated_at": _now_iso(),
            "model_client": "production-like",
            "high_recall": args.high_recall,
            "typed": args.typed,
            "routing_profile": args.routing_profile,
            "max_events_per_call": args.max_events_per_call,
            "memory_snapshot_limit": args.memory_snapshot_limit,
            "session_count": len(session_items),
            "shards": manifest.get("shards", {}),
        }
    )
    _write_json(run_dir / "manifest.json", manifest)

    pipeline = CoreMemoryPipeline(
        model_client=ProductionLikeMemoryModelClient(
            max_events_per_call=args.max_events_per_call,
            high_recall=args.high_recall,
            typed=args.typed,
        )
    )
    completed = 0
    failed = 0
    skipped = 0

    for index, (session_id, session_segments) in enumerate(session_items, start=1):
        run_id = f"export-session-{_safe_id(session_id)}"
        input_path = input_dir / f"{run_id}.json"
        output_path = output_dir / f"{run_id}.json"
        shard = manifest["shards"].get(run_id, {})
        if output_path.exists() and shard.get("status") == "ok" and not args.retry_ok:
            skipped += 1
            _print_progress(index, len(session_items), run_id, "skip", shard)
            continue

        pipeline_input = _build_pipeline_input(
            run_id=run_id,
            session_id=session_id,
            session_segments=session_segments,
            user_state=user_state,
            actor_id=args.actor_id,
            actor_name=args.actor_name,
            routing_profile=args.routing_profile,
        )
        _write_json(input_path, pipeline_input.model_dump(mode="json"))

        try:
            output = await pipeline.run(pipeline_input)
            _write_json(output_path, output.model_dump(mode="json"))
            shard_summary = _output_summary(output.model_dump(mode="json"))
            shard_summary.update(
                {
                    "run_id": run_id,
                    "session_id": session_id,
                    "raw_events": len(session_segments),
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                    "updated_at": _now_iso(),
                }
            )
            manifest["shards"][run_id] = shard_summary
            completed += 1
            _print_progress(index, len(session_items), run_id, output.status, shard_summary)
        except Exception as exc:
            failed += 1
            manifest["shards"][run_id] = {
                "run_id": run_id,
                "session_id": session_id,
                "status": "runner_failed",
                "raw_events": len(session_segments),
                "input_path": str(input_path),
                "output_path": str(output_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "updated_at": _now_iso(),
            }
            _print_progress(index, len(session_items), run_id, "runner_failed", manifest["shards"][run_id])
            if not args.keep_going:
                manifest["updated_at"] = _now_iso()
                _write_json(run_dir / "manifest.json", manifest)
                raise
        manifest["updated_at"] = _now_iso()
        _write_json(run_dir / "manifest.json", manifest)

    _combine_outputs(run_dir)
    trace_report = _write_debug_trace(run_dir)
    summary = _summarize_manifest(manifest)
    summary.update({"completed_this_run": completed, "failed_this_run": failed, "skipped_this_run": skipped})
    summary["debug_trace_jsonl"] = str((run_dir / "debug_trace.jsonl").resolve())
    summary["debug_trace_report"] = trace_report
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


def _read_export(zip_path: str, export_root: str) -> ExportDataset:
    with zipfile.ZipFile(zip_path) as archive:
        segments = cast(
            list[dict[str, Any]], json.loads(archive.read(export_root + "raw_tables/transcription_segments.json"))
        )
        memories = cast(list[dict[str, Any]], json.loads(archive.read(export_root + "raw_tables/memories.json")))
        sessions = cast(
            list[dict[str, Any]], json.loads(archive.read(export_root + "raw_tables/transcription_sessions.json"))
        )
    return ExportDataset(segments=segments, memories=memories, sessions=sessions)


def _build_user_state(memories: list[dict[str, Any]], limit: int) -> UserStateSnapshot:
    if limit <= 0:
        return UserStateSnapshot(
            snapshot_id="empty-export-memory-snapshot",
            snapshot_at=datetime.now(timezone.utc),
            active_memories=[],
            rejected_memories=[],
        )

    active: list[ExistingMemorySnapshot] = []
    rejected: list[ExistingMemorySnapshot] = []
    for memory in memories:
        content = (memory.get("content") or "").strip()
        if not content or memory.get("deleted"):
            continue
        snapshot = ExistingMemorySnapshot(
            memory_id=str(memory.get("id") or memory.get("backendId")),
            text=content,
            kind=str(memory.get("category") or "other"),
            locked=bool(memory.get("isLocked")),
            reviewed=bool(memory.get("reviewed")),
            rejected=memory.get("userReview") is False,
            status="rejected" if memory.get("userReview") is False else "active",
            created_at=_parse_dt(memory.get("createdAt")),
            updated_at=_parse_dt(memory.get("updatedAt")),
            origin="manual" if memory.get("manuallyAdded") else "auto",
        )
        if snapshot.rejected:
            rejected.append(snapshot)
        else:
            active.append(snapshot)
        if len(active) + len(rejected) >= limit:
            break
    return UserStateSnapshot(
        snapshot_id="export-memory-snapshot",
        snapshot_at=datetime.now(timezone.utc),
        active_memories=active,
        rejected_memories=rejected,
    )


def _group_segments_by_session(segments: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        session_id = str(segment.get("sessionId") or "unknown")
        grouped.setdefault(session_id, []).append(segment)
    for session_id, session_segments in grouped.items():
        grouped[session_id] = sorted(session_segments, key=_event_sort_key)
    return grouped


def _build_pipeline_input(
    *,
    run_id: str,
    session_id: str,
    session_segments: list[dict[str, Any]],
    user_state: UserStateSnapshot,
    actor_id: str,
    actor_name: str,
    routing_profile: str,
) -> MemoryPipelineInput:
    events: list[RawContextEvent] = []
    seen_event_ids: set[str] = set()
    for index, segment in enumerate(session_segments):
        event_id = str(segment.get("id") or segment.get("segmentId") or f"segment-{index}")
        if event_id in seen_event_ids:
            event_id = f"{event_id}-{index}"
        seen_event_ids.add(event_id)
        events.append(
            RawContextEvent(
                event_id=event_id,
                event_type="transcript_segment",
                text=(segment.get("text") or "").strip(),
                start_at=_parse_dt(segment.get("startTime") or segment.get("createdAt")),
                end_at=_parse_dt(segment.get("endTime")),
                order=segment.get("segmentOrder") if isinstance(segment.get("segmentOrder"), int) else index,
                source_ref=SourceRef(
                    conversation_id=session_id,
                    transcript_segment_id=str(segment.get("segmentId") or segment.get("id") or index),
                ),
                structured_payload={"export_table": "transcription_segments"},
            )
        )

    return MemoryPipelineInput(
        run_id=run_id,
        mode="offline",
        source=SourceDescriptor(
            source_type="transcript",
            source_id=session_id,
            captured_at=events[0].start_at if events else None,
        ),
        actor=ActorDescriptor(synthetic_user_id=actor_id, display_name=actor_name),
        user_state=user_state,
        raw_events=events,
        config=MemoryPipelineConfig(
            models=ModelConfig(extractor_model="omi-production-like"),
            routing=_routing_config(routing_profile),
        ),
    )


def _routing_config(profile: str) -> RoutingConfig:
    if profile == "default":
        return RoutingConfig()
    if profile == "shadow-safe":
        return RoutingConfig(
            review_uncertain=True,
            auto_create_medium_confidence=False,
            review_low_confidence=True,
            review_sensitive=True,
            allow_supersession=False,
            route_tasks=True,
        )
    raise ValueError(f"unknown routing profile: {profile}")


def _run_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "memory_export_run_config.v1",
        "export_zip": str(Path(args.export_zip).resolve()),
        "export_root": args.export_root,
        "actor_id": args.actor_id,
        "actor_name": args.actor_name,
        "model_client": "production-like",
        "high_recall": args.high_recall,
        "typed": args.typed,
        "routing_profile": args.routing_profile,
        "max_events_per_call": args.max_events_per_call,
        "memory_snapshot_limit": args.memory_snapshot_limit,
        "session_id": args.session_id,
        "limit": args.limit,
    }


def _assert_resume_config_compatible(
    manifest: dict[str, Any], run_config: dict[str, Any], allow_legacy_resume: bool
) -> None:
    if not manifest or not manifest.get("shards"):
        return
    expected = manifest.get("run_config_fingerprint")
    if not expected:
        if allow_legacy_resume:
            return
        raise RuntimeError(
            "Run directory contains shards without a run_config_fingerprint. "
            "Use a fresh --run-dir, or pass --allow-legacy-resume if you have verified the config manually."
        )
    actual = _fingerprint(run_config)
    if expected != actual:
        raise RuntimeError(
            "Run directory config does not match the requested export config. "
            f"existing={expected} requested={actual}. Use a fresh --run-dir."
        )


def _output_summary(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": output["status"],
        "frames": len(output["event_frames"]),
        "decisions": len(output["decisions"]),
        "frame_resolutions": len(output["frame_resolutions"]),
        "triples": len(output["derived_triples"]),
        "creates": len(output["mutation_plan"]["creates"]),
        "updates": len(output["mutation_plan"]["updates"]),
        "invalidations": len(output["mutation_plan"]["invalidations"]),
        "evidence_links": len(output["mutation_plan"]["evidence_links"]),
        "review_items": len(output["review_items"]),
        "rejected_items": len(output["rejected_items"]),
        "task_routes": len(output["mutation_plan"]["task_routes"]),
        "vector_upserts": len(output["vector_plan"]["upserts"]),
        "vector_deletes": len(output["vector_plan"]["deletes"]),
        "errors": len(output["errors"]),
        "lints": len(output["audit"]["lint_results"]),
        "redactions": len(output["audit"]["redactions"]),
    }


def _combine_outputs(run_dir: Path) -> None:
    output_dir = run_dir / "outputs"
    combined_jsonl = run_dir / "combined_outputs.jsonl"
    combined_json = run_dir / "combined_outputs.json"
    outputs: list[dict[str, Any]] = []
    with combined_jsonl.open("w") as jsonl:
        for output_path in sorted(output_dir.glob("*.json")):
            output = cast(dict[str, Any], json.loads(output_path.read_text()))
            outputs.append(output)
            jsonl.write(json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n")
    _write_json(combined_json, outputs)


def _write_debug_trace(run_dir: Path) -> dict[str, Any]:
    output_dir = run_dir / "outputs"
    trace_path = run_dir / "debug_trace.jsonl"
    counters: dict[str, int] = {
        "rows": 0,
        "frames": 0,
        "creates": 0,
        "reviews": 0,
        "rejections": 0,
        "task_routes": 0,
        "evidence_links": 0,
    }
    with trace_path.open("w") as jsonl:
        for output_path in sorted(output_dir.glob("*.json")):
            output = cast(dict[str, Any], json.loads(output_path.read_text()))
            counters["rows"] += 1
            decisions: dict[Any, dict[str, Any]] = {
                decision.get("frame_id"): decision
                for decision in cast(list[dict[str, Any]], output.get("decisions") or [])
            }
            review_items: dict[Any, dict[str, Any]] = {
                item.get("frame_id"): item for item in cast(list[dict[str, Any]], output.get("review_items") or [])
            }
            for frame in cast(list[dict[str, Any]], output.get("event_frames") or []):
                counters["frames"] += 1
                decision: dict[str, Any] = decisions.get(frame.get("frame_id")) or {}
                action = str(decision.get("action") or "no_decision")
                if action == "create_memory":
                    counters["creates"] += 1
                elif action == "route_to_review":
                    counters["reviews"] += 1
                elif action == "route_to_task":
                    counters["task_routes"] += 1
                elif action == "attach_evidence":
                    counters["evidence_links"] += 1
                elif action.startswith("reject_"):
                    counters["rejections"] += 1
                jsonl.write(
                    json.dumps(
                        _debug_trace_row(output, frame, decision, review_items.get(frame.get("frame_id"))),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    return {"path": str(trace_path.resolve()), **counters}


def _debug_trace_row(
    output: dict[str, Any],
    frame: dict[str, Any],
    decision: dict[str, Any],
    review_item: dict[str, Any] | None,
) -> dict[str, Any]:
    frame_evidence = cast(list[dict[str, Any]], frame.get("evidence") or [])
    first_evidence: dict[str, Any] = frame_evidence[0] if frame_evidence else {}
    first_source_ref: dict[str, Any] = cast(dict[str, Any], first_evidence.get("source_ref") or {})
    frame_arguments = cast(dict[str, Any], frame.get("arguments") or {})
    frame_sensitivity = cast(dict[str, Any], frame.get("sensitivity") or {})
    decision_target_ids = cast(list[Any], decision.get("target_memory_ids") or [])
    review = review_item or {}
    evidence_refs: list[dict[str, Any]] = []
    for evidence in cast(list[dict[str, Any]], frame.get("evidence") or []):
        source_ref = cast(dict[str, Any], evidence.get("source_ref") or {})
        speaker = cast(dict[str, Any], evidence.get("speaker") or {})
        evidence_refs.append(
            {
                "source_event_id": evidence.get("source_event_id"),
                "conversation_id": source_ref.get("conversation_id"),
                "transcript_segment_id": source_ref.get("transcript_segment_id"),
                "start_at": evidence.get("start_at"),
                "end_at": evidence.get("end_at"),
                "speaker_label": speaker.get("label"),
            }
        )
    return {
        "run_id": output.get("run_id"),
        "mode": output.get("mode"),
        "status": output.get("status"),
        "source": {
            "conversation_id": first_source_ref.get("conversation_id"),
            "event_ids": frame.get("source_event_ids") or [],
        },
        "frame": {
            "frame_id": frame.get("frame_id"),
            "frame_type": frame.get("frame_type"),
            "predicate": frame.get("predicate"),
            "canonical_text": frame.get("canonical_text"),
            "subject": _entity_name(frame.get("subject")),
            "arguments": _trace_arguments(frame_arguments),
            "confidence": frame.get("confidence"),
            "uncertainty_reasons": frame.get("uncertainty_reasons") or [],
            "sensitivity": frame_sensitivity,
            "durability": frame.get("durability"),
            "scope": frame.get("scope"),
        },
        "decision": {
            "decision_id": decision.get("decision_id"),
            "action": decision.get("action"),
            "rationale": decision.get("rationale"),
            "target_memory_ids": decision_target_ids,
        },
        "review": {
            "review_id": review.get("review_id"),
            "reason": review.get("reason"),
        },
        "evidence_refs": evidence_refs,
    }


def _trace_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: _object_value(value) for key, value in sorted(arguments.items())}


def _object_value(value: Any) -> Any:
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        entity = cast(dict[str, Any], d.get("entity") or {})
        return d.get("value") or entity.get("canonical_name") or entity.get("entity_id")
    return value


def _entity_name(value: Any) -> str | None:
    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        return d.get("canonical_name") or d.get("entity_id")
    return None


def _summarize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    shards = list(manifest.get("shards", {}).values())
    ok = [shard for shard in shards if shard.get("status") == "ok"]
    partial = [shard for shard in shards if shard.get("status") == "partial"]
    runner_failed = [shard for shard in shards if shard.get("status") == "runner_failed"]
    failed = [shard for shard in shards if shard.get("status") not in ("ok", "partial")]
    totals = {
        key: sum(int(shard.get(key, 0) or 0) for shard in ok)
        for key in [
            "raw_events",
            "frames",
            "decisions",
            "triples",
            "creates",
            "updates",
            "invalidations",
            "review_items",
            "rejected_items",
            "task_routes",
            "vector_upserts",
            "vector_deletes",
            "errors",
            "lints",
            "redactions",
        ]
    }
    return {
        "schema_version": "memory_export_run_summary.v1",
        "run_dir": manifest["run_dir"],
        "updated_at": _now_iso(),
        "session_count": manifest["session_count"],
        "shards_recorded": len(shards),
        "ok_shards": len(ok),
        "partial_shards": len(partial),
        "runner_failed_shards": len(runner_failed),
        "failed_shards": len(failed),
        "totals": totals,
        "combined_jsonl": str(Path(manifest["run_dir"]) / "combined_outputs.jsonl"),
        "combined_json": str(Path(manifest["run_dir"]) / "combined_outputs.json"),
        "manifest": str(Path(manifest["run_dir"]) / "manifest.json"),
    }


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(path)
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_json(path: Path, value: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str))
    tmp_path.replace(path)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _print_progress(index: int, total: int, run_id: str, status: str, summary: dict[str, Any]) -> None:
    print(
        json.dumps(
            {
                "index": index,
                "total": total,
                "run_id": run_id,
                "status": status,
                "raw_events": summary.get("raw_events"),
                "frames": summary.get("frames"),
                "creates": summary.get("creates"),
                "errors": summary.get("errors"),
                "lints": summary.get("lints"),
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _event_sort_key(segment: dict[str, Any]) -> tuple[float, int, str]:
    dt = _parse_dt(segment.get("startTime") or segment.get("createdAt"))
    return (dt.timestamp() if dt else 0.0, int(segment.get("segmentOrder") or 0), str(segment.get("id") or ""))


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")
    return safe[:120] or "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-export-runner")
    parser.add_argument("--export-zip", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--export-root", default=DEFAULT_EXPORT_ROOT)
    parser.add_argument("--actor-id", default="export-bigbeeme33")
    parser.add_argument("--actor-name", default="User")
    parser.add_argument("--max-events-per-call", type=int, default=80)
    parser.add_argument(
        "--high-recall",
        action="store_true",
        help="Use the benchmark/high-recall extraction schema instead of the capped production memory schema.",
    )
    parser.add_argument(
        "--typed",
        action="store_true",
        help="Use the typed extraction prompt (predicate + argument slots) so layer-2 consolidation can merge.",
    )
    parser.add_argument(
        "--routing-profile",
        choices=["default", "shadow-safe"],
        default="default",
        help="Routing profile for rollout/benchmark runs. shadow-safe routes uncertain frames to review and avoids supersession.",
    )
    parser.add_argument("--memory-snapshot-limit", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--session-id")
    parser.add_argument("--retry-ok", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument(
        "--allow-legacy-resume",
        action="store_true",
        help="Resume a pre-fingerprint run directory after manually verifying the requested config matches.",
    )
    args = parser.parse_args()
    asyncio.run(run_export(args))


if __name__ == "__main__":
    main()
