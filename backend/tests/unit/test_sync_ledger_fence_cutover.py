from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import pytest

from scripts import sync_ledger_fence_cutover as cutover

CANDIDATE_IMAGE = "gcr.io/omi/backend@sha256:" + "a" * 64


def _write_passing_probe_evidence(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "suite": cutover.PROBE_EVIDENCE_SUITE,
                "status": "PASS",
                "full_route_authoritative": True,
                "direct_diagnostic_only": True,
                "checks": [
                    {
                        "name": "full_route",
                        "status": "PASS",
                        "details": {
                            "configured": True,
                            "fixture_available": True,
                            "json_object": True,
                            "outcome_success": True,
                            "phrase_match": True,
                            "provider_checked": True,
                            "provider_match": True,
                            "model_checked": True,
                            "model_match": True,
                            "authority": "candidate_gate",
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _argument(command: Sequence[str], prefix: str) -> str | None:
    return next((part[len(prefix) :] for part in command if part.startswith(prefix)), None)


class FakeCloudRunner:
    """In-memory Cloud Run/Tasks runner; tests never invoke gcloud."""

    def __init__(
        self,
        *,
        fail_revision_delete: bool = False,
        fail_promotion_once: bool = False,
        fail_promotion_for_service: str | None = None,
        queue_states: dict[str, str] | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.fail_revision_delete = fail_revision_delete
        self.fail_promotion_once = fail_promotion_once
        self.fail_promotion_for_service = fail_promotion_for_service
        self.queues = queue_states or {"sync-jobs": "RUNNING", "sync-backfill": "PAUSED"}
        self.services: dict[str, dict] = {}
        self.revisions: dict[str, dict] = {}
        self.revision_service: dict[str, str] = {}
        for service in cutover.SERVICES:
            revision = f"{service}-legacy"
            self.revision_service[revision] = service
            self.revisions[revision] = self._revision_document(
                revision=revision,
                image="gcr.io/omi/backend@sha256:" + "b" * 64,
                mode="legacy",
            )
            self.services[service] = self._service_document(
                latest=revision,
                traffic=[{"revisionName": revision, "percent": 100}],
                image="gcr.io/omi/backend@sha256:" + "b" * 64,
                mode="legacy",
            )

    @staticmethod
    def _environment(mode: str) -> list[dict[str, str]]:
        return [
            {"name": "OMI_ENV_STAGE", "value": "prod"},
            {"name": cutover.FENCE_MODE_ENV, "value": mode},
        ]

    def _revision_document(self, *, revision: str, image: str, mode: str) -> dict:
        return {
            "metadata": {"name": revision},
            "spec": {"containers": [{"image": image, "env": self._environment(mode)}]},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }

    def _service_document(self, *, latest: str, traffic: list[dict], image: str, mode: str) -> dict:
        return {
            "spec": {"template": {"spec": {"containers": [{"image": image, "env": self._environment(mode)}]}}},
            "status": {
                "latestCreatedRevisionName": latest,
                "latestReadyRevisionName": latest,
                "traffic": traffic,
            },
        }

    @staticmethod
    def _json(document: dict) -> cutover.CommandResult:
        return cutover.CommandResult(returncode=0, stdout=json.dumps(document))

    def run(self, command: Sequence[str], *, check: bool = True) -> cutover.CommandResult:
        command = list(command)
        self.commands.append(command)
        if command[:4] == ["gcloud", "run", "services", "describe"]:
            return self._json(self.services[command[4]])
        if command[:4] == ["gcloud", "run", "services", "update"]:
            return self._deploy(command)
        if command[:4] == ["gcloud", "run", "revisions", "describe"]:
            revision = command[4]
            if revision not in self.revisions:
                return cutover.CommandResult(returncode=1)
            return self._json(self.revisions[revision])
        if command[:4] == ["gcloud", "run", "revisions", "list"]:
            service = _argument(command, "--service=")
            assert service is not None
            return self._json(
                [
                    {"metadata": {"name": revision}}
                    for revision, revision_service in self.revision_service.items()
                    if revision_service == service
                ]
            )
        if command[:4] == ["gcloud", "run", "revisions", "delete"]:
            return self._delete_revision(command, check=check)
        if command[:4] == ["gcloud", "run", "services", "update-traffic"]:
            return self._update_traffic(command)
        if command[:4] == ["gcloud", "tasks", "queues", "describe"]:
            return self._json({"state": self.queues[command[4]]})
        if command[:4] == ["gcloud", "tasks", "queues", "pause"]:
            self.queues[command[4]] = "PAUSED"
            return cutover.CommandResult(returncode=0)
        if command[:4] == ["gcloud", "tasks", "queues", "resume"]:
            self.queues[command[4]] = "RUNNING"
            return cutover.CommandResult(returncode=0)
        raise AssertionError(f"unexpected command: {command}")

    def _deploy(self, command: list[str]) -> cutover.CommandResult:
        service = command[4]
        image = _argument(command, "--image=")
        mode_assignment = _argument(command, "--update-env-vars=")
        suffix = _argument(command, "--revision-suffix=")
        assert image is not None and mode_assignment is not None and suffix is not None
        assert mode_assignment.startswith(f"{cutover.FENCE_MODE_ENV}=")
        mode = mode_assignment.split("=", maxsplit=1)[1]
        revision = f"{service}-{suffix}"
        self.revision_service[revision] = service
        self.revisions[revision] = self._revision_document(revision=revision, image=image, mode=mode)
        prior = self.services[service]
        traffic = list(prior["status"]["traffic"])
        tag = _argument(command, "--tag=")
        if tag:
            traffic.append(
                {
                    "revisionName": revision,
                    "percent": 0,
                    "tag": tag,
                    "url": f"https://{tag}---{service}.example.test",
                }
            )
        self.services[service] = self._service_document(
            latest=revision,
            traffic=traffic,
            image=image,
            mode=mode,
        )
        return cutover.CommandResult(returncode=0)

    def _delete_revision(self, command: list[str], *, check: bool) -> cutover.CommandResult:
        revision = command[4]
        if self.fail_revision_delete:
            if check:
                raise cutover.CutoverError("injected revision deletion failure")
            return cutover.CommandResult(returncode=1)
        self.revisions.pop(revision, None)
        self.revision_service.pop(revision, None)
        return cutover.CommandResult(returncode=0)

    def _update_traffic(self, command: list[str]) -> cutover.CommandResult:
        service = command[4]
        traffic_target = _argument(command, "--to-revisions=")
        remove_tags = _argument(command, "--remove-tags=")
        current = self.services[service]
        if traffic_target:
            if self.fail_promotion_once or self.fail_promotion_for_service == service:
                self.fail_promotion_once = False
                self.fail_promotion_for_service = None
                raise cutover.CutoverError("injected traffic promotion failure")
            revision, percent = traffic_target.rsplit("=", maxsplit=1)
            current["status"]["traffic"] = [target for target in current["status"]["traffic"] if target.get("tag")] + [
                {"revisionName": revision, "percent": int(percent)}
            ]
        elif remove_tags:
            tags = set(remove_tags.split(","))
            current["status"]["traffic"] = [
                target for target in current["status"]["traffic"] if target.get("tag") not in tags
            ]
        else:
            raise AssertionError(f"unexpected traffic operation: {command}")
        return cutover.CommandResult(returncode=0)


def _config(tmp_path: Path, *, suffix: str = "cutover-123-1-standby") -> cutover.CutoverConfig:
    return cutover.CutoverConfig(
        project="omi-prod",
        region="us-central1",
        candidate_image=CANDIDATE_IMAGE,
        state_path=tmp_path / "state.json",
        revision_suffix=suffix,
        poll_attempts=1,
        poll_interval_seconds=0,
    )


def _orchestrator(
    config: cutover.CutoverConfig,
    runner: FakeCloudRunner,
    *,
    mode: str,
) -> cutover.CutoverOrchestrator:
    return cutover.CutoverOrchestrator(
        config,
        runner=runner,
        sleep=lambda _: None,
        environ={cutover.FENCE_MODE_ENV: mode},
    )


def test_command_builder_uses_immutable_no_traffic_update_contract() -> None:
    command = cutover.build_deploy_candidate_command(
        project="omi-prod",
        region="us-central1",
        service="backend-sync",
        candidate_image=CANDIDATE_IMAGE,
        mode="standby",
        revision_suffix="cutover-123-1-standby",
    )

    assert "--no-traffic" in command
    assert f"--image={CANDIDATE_IMAGE}" in command
    assert f"--update-env-vars={cutover.FENCE_MODE_ENV}=standby" in command
    assert not any(part.startswith("--set-env-vars") for part in command)
    assert "--revision-suffix=cutover-123-1-standby" in command


def test_cutover_workflow_keeps_protected_candidate_gate_and_no_failure_resume_contract() -> None:
    workflow = (
        Path(__file__).resolve().parents[3] / ".github" / "workflows" / "sync_ledger_fence_cutover.yml"
    ).read_text(encoding="utf-8")

    assert "group: deploy-backend-stack-${{ github.event.inputs.environment }}" in workflow
    assert "candidate_image must be an immutable @sha256 digest" in workflow
    assert 'python3 backend/scripts/transcription_capability_probe.py' in workflow
    assert '--candidate-api-url "$CANDIDATE_PROBE_URL"' in workflow
    assert "--require-route-identity" in workflow
    assert "OMI_TRANSCRIPTION_SYNTHETIC_AUDIO_URL: ${{ secrets.OMI_TRANSCRIPTION_SYNTHETIC_AUDIO_URL }}" in workflow
    assert "sync_ledger_fence_cutover.py activate-promote" in workflow
    assert "gcloud tasks queues resume" not in workflow
    assert "Plan safe activation recovery from persisted phase" in workflow
    assert "active_probe_passed" in workflow
    assert "if: steps.activation-plan.outputs.probe == 'true'" in workflow
    assert "if: steps.activation-plan.outputs.promote == 'true'" in workflow


def test_stage_then_active_promotion_uses_artifact_and_resumes_only_original_running_queue(tmp_path: Path) -> None:
    runner = FakeCloudRunner()
    stage_config = _config(tmp_path)

    stage_state = _orchestrator(stage_config, runner, mode="standby").stage()

    assert stage_state["phase"] == cutover.STAGE_COMPLETE
    assert stage_state["queues"]["sync-jobs"]["recorded_state"] == "RUNNING"
    assert stage_state["queues"]["sync-backfill"]["recorded_state"] == "PAUSED"
    assert runner.queues == {"sync-jobs": "PAUSED", "sync-backfill": "PAUSED"}
    assert set(runner.revisions) == {f"{service}-cutover-123-1-standby" for service in cutover.SERVICES}

    active_config = _config(tmp_path, suffix="cutover-123-1-active")
    github_output = tmp_path / "github-output"
    prepared = _orchestrator(active_config, runner, mode="active").activate_prepare(
        probe_tag="ledger-123-1",
        github_output=github_output,
    )

    assert prepared["phase"] == cutover.ACTIVE_READY_FOR_PROBE
    assert prepared["probe"]["revision"] == "backend-cutover-123-1-active"
    assert (
        github_output.read_text(encoding="utf-8") == "candidate_probe_url=https://ledger-123-1---backend.example.test\n"
    )
    assert any("--tag=ledger-123-1" in command for command in runner.commands)

    evidence = tmp_path / "candidate-probe.json"
    _write_passing_probe_evidence(evidence)
    _orchestrator(active_config, runner, mode="active").record_probe_success(evidence_path=evidence)
    final_state = _orchestrator(active_config, runner, mode="active").activate_promote(probe_tag="ledger-123-1")

    assert final_state["phase"] == cutover.ACTIVE_COMPLETE
    assert runner.queues == {"sync-jobs": "RUNNING", "sync-backfill": "PAUSED"}
    assert final_state["queues"]["sync-jobs"]["resumed_by_cutover"] is True
    assert final_state["queues"]["sync-backfill"]["resumed_by_cutover"] is False
    assert "backend-cutover-123-1-active" in runner.revisions
    assert "backend-cutover-123-1-standby" not in runner.revisions
    assert all("--remove-tags=ledger-123-1" not in command or command[4] == "backend" for command in runner.commands)
    resume_commands = [command for command in runner.commands if command[:4] == ["gcloud", "tasks", "queues", "resume"]]
    assert [command[4] for command in resume_commands] == ["sync-jobs"]


def test_stage_cleanup_failure_never_resumes_queues_after_pause(tmp_path: Path) -> None:
    runner = FakeCloudRunner(fail_revision_delete=True)
    orchestrator = _orchestrator(_config(tmp_path), runner, mode="standby")

    with pytest.raises(cutover.CutoverError, match="injected revision deletion failure"):
        orchestrator.stage()

    state = cutover.load_state(_config(tmp_path).state_path)
    assert state["phase"] == "queues_paused"
    assert runner.queues == {"sync-jobs": "PAUSED", "sync-backfill": "PAUSED"}
    assert not any(command[:4] == ["gcloud", "tasks", "queues", "resume"] for command in runner.commands)


def test_stage_refuses_to_overwrite_partial_queue_artifact(tmp_path: Path) -> None:
    runner = FakeCloudRunner(queue_states={"sync-jobs": "PAUSED", "sync-backfill": "PAUSED"})
    config = _config(tmp_path)
    partial_state = cutover._new_state(config, mode="standby")
    partial_state["phase"] = "queues_paused"
    partial_state["queues"] = {
        "sync-jobs": {
            "recorded_state": "RUNNING",
            "verified_paused": True,
            "paused_by_cutover": True,
            "resumed_by_cutover": False,
        },
        "sync-backfill": {
            "recorded_state": "PAUSED",
            "verified_paused": True,
            "paused_by_cutover": False,
            "resumed_by_cutover": False,
        },
    }
    cutover.write_state(config.state_path, partial_state)

    with pytest.raises(cutover.CutoverError, match="refusing to overwrite incomplete standby state"):
        _orchestrator(config, runner, mode="standby").stage()

    preserved = cutover.load_state(config.state_path)
    assert preserved["queues"]["sync-jobs"]["recorded_state"] == "RUNNING"
    assert runner.commands == []


def test_stage_promotes_all_standby_admission_surfaces_before_pausing_queues(tmp_path: Path) -> None:
    runner = FakeCloudRunner()

    _orchestrator(_config(tmp_path), runner, mode="standby").stage()

    first_pause = next(
        index for index, command in enumerate(runner.commands) if command[:4] == ["gcloud", "tasks", "queues", "pause"]
    )
    standby_promotions = [
        index
        for index, command in enumerate(runner.commands)
        if command[:4] == ["gcloud", "run", "services", "update-traffic"]
        and "cutover-123-1-standby=100" in " ".join(command)
    ]

    assert len(standby_promotions) == len(cutover.SERVICES)
    assert max(standby_promotions) < first_pause


@pytest.mark.parametrize("mode", ["legacy", "standby", ""])
def test_activation_rejects_non_active_mode_before_any_cloud_command(tmp_path: Path, mode: str) -> None:
    runner = FakeCloudRunner()
    config = _config(tmp_path, suffix="cutover-123-1-active")
    state = cutover._new_state(config, mode="standby")
    state["phase"] = cutover.STAGE_COMPLETE
    cutover.write_state(config.state_path, state)

    with pytest.raises(cutover.CutoverError, match="must read back as 'active'"):
        _orchestrator(config, runner, mode=mode).activate_prepare(probe_tag="ledger-123-1")

    assert runner.commands == []


def test_active_prepare_refuses_stage_artifact_when_queues_are_not_paused(tmp_path: Path) -> None:
    runner = FakeCloudRunner(queue_states={"sync-jobs": "RUNNING", "sync-backfill": "PAUSED"})
    stage_config = _config(tmp_path)
    _orchestrator(stage_config, runner, mode="standby").stage()
    runner.queues["sync-jobs"] = "RUNNING"  # Drift after stage is an unsafe activation precondition.
    active_config = _config(tmp_path, suffix="cutover-123-1-active")
    commands_before_activation = len(runner.commands)

    with pytest.raises(cutover.CutoverError, match="no longer paused"):
        _orchestrator(active_config, runner, mode="active").activate_prepare(probe_tag="ledger-123-1")

    assert not any(
        command[:4] == ["gcloud", "run", "services", "update"]
        for command in runner.commands[commands_before_activation:]
    )


def test_probe_evidence_must_prove_full_route_transcript_and_route_identity(tmp_path: Path) -> None:
    runner = FakeCloudRunner()
    stage_config = _config(tmp_path)
    _orchestrator(stage_config, runner, mode="standby").stage()
    active_config = _config(tmp_path, suffix="cutover-123-1-active")
    active = _orchestrator(active_config, runner, mode="active")
    active.activate_prepare(probe_tag="ledger-123-1")
    evidence = tmp_path / "candidate-probe.json"
    evidence.write_text('{"suite":"omi_transcription_capability_probe","status":"PASS"}\n', encoding="utf-8")

    with pytest.raises(cutover.CutoverError, match="did not mark the full route authoritative"):
        active.record_probe_success(evidence_path=evidence)

    assert cutover.load_state(active_config.state_path)["phase"] == cutover.ACTIVE_READY_FOR_PROBE
    commands_before_recovery = len(runner.commands)
    recovered_output = tmp_path / "recovered-github-output"
    recovered = active.activate_prepare(probe_tag="ledger-123-1", github_output=recovered_output)

    assert recovered["phase"] == cutover.ACTIVE_READY_FOR_PROBE
    assert runner.queues == {"sync-jobs": "PAUSED", "sync-backfill": "PAUSED"}
    assert not any(
        command[:4] == ["gcloud", "run", "services", "update"] for command in runner.commands[commands_before_recovery:]
    )
    assert (
        recovered_output.read_text(encoding="utf-8")
        == "candidate_probe_url=https://ledger-123-1---backend.example.test\n"
    )

    _write_passing_probe_evidence(evidence)
    active.record_probe_success(evidence_path=evidence)
    assert cutover.load_state(active_config.state_path)["phase"] == cutover.ACTIVE_PROBE_PASSED
    # The workflow skips this step after recovery, but the state transition is
    # also safe when the command itself is retried without its old evidence.
    active.record_probe_success(evidence_path=tmp_path / "missing-after-pass.json")


def test_active_promotion_retries_after_probe_tag_was_already_removed(tmp_path: Path) -> None:
    runner = FakeCloudRunner()
    stage_config = _config(tmp_path)
    _orchestrator(stage_config, runner, mode="standby").stage()
    active_config = _config(tmp_path, suffix="cutover-123-1-active")
    active = _orchestrator(active_config, runner, mode="active")
    active.activate_prepare(probe_tag="ledger-123-1")
    evidence = tmp_path / "candidate-probe.json"
    _write_passing_probe_evidence(evidence)
    active.record_probe_success(evidence_path=evidence)
    runner.fail_promotion_for_service = "backend-sync"
    with pytest.raises(cutover.CutoverError, match="injected traffic promotion failure"):
        active.activate_promote(probe_tag="ledger-123-1")

    state_after_failure = cutover.load_state(active_config.state_path)
    assert state_after_failure["phase"] == cutover.ACTIVE_PROBE_PASSED
    assert state_after_failure["probe_tag_removed"] is True
    assert cutover.traffic_by_revision(runner.services["backend"])["backend-cutover-123-1-active"] == 100
    first_remove_count = sum("--remove-tags=ledger-123-1" in command for command in runner.commands)
    backend_promote_count = sum(
        "--to-revisions=backend-cutover-123-1-active=100" in command for command in runner.commands
    )

    final_state = _orchestrator(active_config, runner, mode="active").activate_promote(probe_tag="ledger-123-1")

    assert final_state["phase"] == cutover.ACTIVE_COMPLETE
    assert sum("--remove-tags=ledger-123-1" in command for command in runner.commands) == first_remove_count
    assert (
        sum("--to-revisions=backend-cutover-123-1-active=100" in command for command in runner.commands)
        == backend_promote_count
    )
    commands_after_complete = len(runner.commands)
    assert _orchestrator(active_config, runner, mode="active").activate_promote(probe_tag="ledger-123-1") == final_state
    assert len(runner.commands) == commands_after_complete


def test_state_parser_rejects_candidate_image_mismatch_without_cloud_call(tmp_path: Path) -> None:
    runner = FakeCloudRunner()
    stage_config = _config(tmp_path)
    state = cutover._new_state(stage_config, mode="standby")
    state["phase"] = cutover.STAGE_COMPLETE
    cutover.write_state(stage_config.state_path, state)
    other_image = "gcr.io/omi/backend@sha256:" + "c" * 64
    active_config = cutover.CutoverConfig(
        project=stage_config.project,
        region=stage_config.region,
        candidate_image=other_image,
        state_path=stage_config.state_path,
        revision_suffix="cutover-123-1-active",
        poll_attempts=1,
        poll_interval_seconds=0,
    )

    with pytest.raises(cutover.CutoverError, match="different candidate image"):
        _orchestrator(active_config, runner, mode="active").activate_prepare(probe_tag="ledger-123-1")

    assert runner.commands == []
