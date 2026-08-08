import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


def _read(relative_path: str) -> str:
    return (REPO_DIR / relative_path).read_text(encoding="utf-8")


def _release_module():
    path = BACKEND_DIR / "scripts" / "agent_vm_release.py"
    spec = importlib.util.spec_from_file_location("agent_vm_release_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_renderer_rejects_the_runtime_invalid_service_account_format():
    release = _release_module()
    payload = {
        "schemaVersion": 1,
        "environment": "development",
        "sourceSha": "a" * 40,
        "imageDigest": f"gcr.io/project/agent-vm@sha256:{'b' * 64}",
        "startupUri": "gs://bucket/agent-vm/releases/startup.sh",
        "startupSha256": "c" * 64,
        "bootImage": "projects/project/global/images/omi-agent-20260805",
        "serviceAccount": "not-a-service-account",
    }

    with pytest.raises(ValueError, match="serviceAccount"):
        release.validate_manifest(payload)


def test_release_renderer_emits_a_hash_covered_dev_only_migration_plan(tmp_path):
    release = _release_module()
    output = tmp_path / "migration.json"
    assert (
        release.main(
            [
                "--output",
                str(output),
                "--environment",
                "development",
                "--source-sha",
                "a" * 40,
                "--image-digest",
                f"gcr.io/project/agent-vm@sha256:{'b' * 64}",
                "--startup-uri",
                "gs://bucket/agent-vm/releases/startup.sh",
                "--startup-sha256",
                "c" * 64,
                "--boot-image",
                "projects/project/global/images/omi-agent-20260805",
                "--service-account",
                "omi-agent-vm-bootstrap@project.iam.gserviceaccount.com",
                "--boot-image-migration-allowed-uid",
                "dev-owner",
                "--boot-image-migration-soak-seconds",
                "60",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bootImageMigration"] == {
        "enabled": True,
        "allowedUids": ["dev-owner"],
        "maxConcurrency": 1,
        "soakSeconds": 60,
        "retentionSeconds": 60,
        "drainRunning": False,
    }
    release.validate_manifest(payload)


def test_release_renderer_emits_only_a_one_owner_seven_day_production_canary(tmp_path):
    release = _release_module()
    output = tmp_path / "migration.json"
    base_args = [
        "--output",
        str(output),
        "--environment",
        "production",
        "--source-sha",
        "a" * 40,
        "--image-digest",
        f"gcr.io/based-hardware/agent-vm@sha256:{'b' * 64}",
        "--startup-uri",
        "gs://based-hardware-agent/agent-vm/releases/startup.sh",
        "--startup-sha256",
        "c" * 64,
        "--boot-image",
        "projects/based-hardware/global/images/omi-agent-20260805",
        "--service-account",
        "omi-agent-vm-bootstrap@based-hardware.iam.gserviceaccount.com",
        "--boot-image-migration-allowed-uid",
        "canary-owner",
    ]
    with pytest.raises(ValueError, match="production"):
        release.render_manifest(release.parser().parse_args(base_args))

    assert (
        release.main(
            base_args
            + [
                "--boot-image-migration-soak-seconds",
                "600",
                "--boot-image-migration-retention-seconds",
                str(7 * 24 * 60 * 60),
                "--boot-image-migration-drain-running",
                "--boot-image-migration-approval-policy",
                "state-preserving-v1",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bootImageMigration"] == {
        "enabled": True,
        "allowedUids": ["canary-owner"],
        "maxConcurrency": 1,
        "soakSeconds": 600,
        "retentionSeconds": 604800,
        "drainRunning": True,
        "approvalPolicy": "state-preserving-v1",
    }
    release.validate_manifest(payload)


def test_prod_migration_activator_is_generation_guarded_and_scheduler_paused():
    script = _read("backend/scripts/activate-agent-vm-prod-migration.sh")

    assert "AGENT_VM_MIGRATION_EXPECTED_ACTIVE_GENERATION" in script
    assert 'scheduler_state' in script and '"PAUSED"' in script
    assert 'project" != "based-hardware"' in script
    assert 'bucket" != "based-hardware-agent"' in script
    assert "state-preserving-v1" in script
    assert "7 * 24 * 60 * 60" in script
    assert "production migration must extend the exact active normal release" in script
    assert '--if-generation-match="$expected_generation"' in script
    assert "scheduler remains PAUSED" in script


def test_desktop_workflows_guard_active_pointer_reads_writes_and_cleanup_rollbacks():
    for workflow in ("desktop_backend_auto_dev.yml", "desktop_backend_prod.yml"):
        text = _read(f".github/workflows/{workflow}")

        assert "gcloud storage objects describe" in text
        assert "NOT_FOUND" in text
        assert "--if-generation-match" in text
        assert "--cache-control='no-store,max-age=0'" in text
        assert "agent-vm-active-activated.generation" in text
        assert "DESKTOP_BACKEND_PROMOTION_COMPLETED=true" in text
        assert "env.DESKTOP_BACKEND_PROMOTION_COMPLETED != 'true'" in text
        assert "global/images/family/omi-agent" not in text
        assert "gcloud compute images describe-from-family omi-agent" in text
        assert "projects/$PROJECT_ID/global/images/$boot_image_name" in text


def test_production_workflow_stages_release_renderer_before_checkouting_admitted_sha():
    workflow = _read(".github/workflows/desktop_backend_prod.yml")

    assert 'cp .workflow-source/backend/scripts/agent_vm_release.py "$controls/backend/scripts/"' in workflow
    assert 'python3 "$DESKTOP_BACKEND_CONTROLS/backend/scripts/agent_vm_release.py"' in workflow
    # The reconciler deploy must be guarded so a pre-reconciler release_sha
    # does not silently leave a stale or broken Cloud Run Job image.
    assert "AGENT_VM_RECONCILER_AVAILABLE" in workflow
    assert "git cat-file -e" in workflow
    assert "backend/jobs/agent_vm_reconciler.py" in workflow


def test_scheduler_apply_resumes_existing_trigger_then_validates_exact_contract():
    script = _read("backend/scripts/apply-agent-vm-reconciler-scheduler.sh")

    assert "gcloud scheduler jobs update http" in script
    assert "gcloud scheduler jobs resume" in script
    assert "gcloud scheduler jobs pause" in script
    assert "AGENT_VM_RECONCILER_SCHEDULER_PAUSED" in script
    assert "validate_agent_vm_reconciler_scheduler.py" in script
    assert "--scheduler-service-account \"$scheduler_sa\"" in script
    assert '--expected-state "$expected_state"' in script


def test_reconciler_iam_installer_refuses_by_default_and_keeps_bindings_scoped(tmp_path):
    script = _read("backend/scripts/apply-agent-vm-reconciler-iam.sh")

    assert 'AGENT_VM_RECONCILER_IAM_APPLY:-}' in script
    assert "REFUSED:" in script
    assert (
        "compute.disks.create,compute.disks.delete,compute.disks.get,compute.disks.setLabels,compute.disks.update,compute.disks.use,compute.disks.useReadOnly,compute.images.useReadOnly,compute.instances.attachDisk,compute.instances.create,compute.instances.delete,compute.instances.detachDisk,compute.instances.get,compute.instances.setDiskAutoDelete,compute.instances.setLabels,compute.instances.setMetadata,compute.instances.setServiceAccount,compute.instances.setTags,compute.instances.start,compute.instances.stop"
        in script
    )
    assert "compute.disks.setLabels" in script
    assert 'subnetwork_permissions="compute.subnetworks.use,compute.subnetworks.useExternalIp"' in script
    assert "Agent VM reconciler instance scope" in script
    assert "Agent VM reconciler disk scope" in script
    assert "compute.googleapis.com/Disk" in script
    assert "disks/omi-agent-" in script
    assert "instances/omi-agent-" in script
    assert "compute networks subnets add-iam-policy-binding default" in script
    assert '--region="$region"' in script
    assert '--role="$subnetwork_role"' in script
    assert "roles/storage.objectViewer" in script
    assert "roles/iam.serviceAccountUser" in script
    assert 'AGENT_VM_RECONCILER_DEPLOYER:-}' in script
    assert "AGENT_VM_RECONCILER_DEPLOYER must be a full Google service-account email." in script

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "gcloud.log"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in\n"
        "    --condition=None) ;;\n"
        "    --condition=*)\n"
        "      IFS=',' read -r -a fields <<< \"${arg#--condition=}\"\n"
        "      [[ \"${#fields[@]}\" == 3 ]] || exit 64\n"
        "      seen_title=0 seen_description=0 seen_expression=0\n"
        "      for field in \"${fields[@]}\"; do\n"
        "        key=\"${field%%=*}\"\n"
        "        value=\"${field#*=}\"\n"
        "        [[ -n \"$value\" ]] || exit 64\n"
        "        case \"$key\" in\n"
        "          title) seen_title=1 ;;\n"
        "          description) seen_description=1 ;;\n"
        "          expression) seen_expression=1 ;;\n"
        "          *) exit 64 ;;\n"
        "        esac\n"
        "      done\n"
        "      [[ \"$seen_title$seen_description$seen_expression\" == 111 ]] || exit 64\n"
        "      ;;\n"
        "  esac\n"
        "done\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_GCLOUD_LOG\"\n"
        "if [[ \"$*\" == projects\\ get-iam-policy* && \"${FAKE_GCLOUD_LEGACY_DISK_BINDING:-}\" == 1 ]]; then\n"
        "  printf '%s\\n' 'Boot disk reads for omi-agent instances in the Agent VM zone'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)
    base_env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_GCLOUD_LOG": str(command_log),
        "AGENT_VM_RECONCILER_IAM_APPLY": "1",
        "AGENT_VM_RECONCILER_PROJECT": "based-hardware-dev",
        "AGENT_VM_RECONCILER_BUCKET": "based-hardware-dev-agent",
        "AGENT_VM_RECONCILER_DEPLOYER": "",
    }

    missing_deployer = subprocess.run(
        ["bash", "backend/scripts/apply-agent-vm-reconciler-iam.sh"],
        cwd=REPO_DIR,
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_deployer.returncode == 2
    assert "AGENT_VM_RECONCILER_DEPLOYER" in missing_deployer.stderr
    assert not command_log.exists(), "the missing-input guard must run before any gcloud mutation"

    malformed_deployer = subprocess.run(
        ["bash", "backend/scripts/apply-agent-vm-reconciler-iam.sh"],
        cwd=REPO_DIR,
        env={
            **base_env,
            "AGENT_VM_RECONCILER_DEPLOYER": "not-an-email",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert malformed_deployer.returncode == 2
    assert "AGENT_VM_RECONCILER_DEPLOYER must be a full Google service-account email." in malformed_deployer.stderr
    assert not command_log.exists(), "invalid deployer input must be rejected before any gcloud mutation"

    completed = subprocess.run(
        ["bash", "backend/scripts/apply-agent-vm-reconciler-iam.sh"],
        cwd=REPO_DIR,
        env={
            **base_env,
            "AGENT_VM_RECONCILER_DEPLOYER": "local-development-joan@based-hardware-dev.iam.gserviceaccount.com",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert (
        "iam service-accounts add-iam-policy-binding "
        "agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--project=based-hardware-dev "
        "--member=serviceAccount:local-development-joan@based-hardware-dev.iam.gserviceaccount.com "
        "--role=roles/iam.serviceAccountUser --condition=None"
    ) in commands
    assert (
        "--condition=title=Agent VM reconciler disk scope,description=Agent VM boot and state disk lifecycle "
        "operations in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Disk' && "
        "resource.name.startsWith('projects/based-hardware-dev/zones/us-central1-a/disks/omi-agent-')"
    ) in commands
    assert (
        "projects add-iam-policy-binding based-hardware-dev "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=projects/based-hardware-dev/roles/omiAgentVmReconcilerOperations --condition=None"
    ) in commands
    assert (
        "compute networks subnets add-iam-policy-binding default --project=based-hardware-dev --region=us-central1 "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=projects/based-hardware-dev/roles/omiAgentVmReconcilerSubnetwork"
    ) in commands
    assert (
        "projects add-iam-policy-binding based-hardware-dev "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=roles/datastore.user --condition=None"
    ) in commands
    assert (
        "storage buckets add-iam-policy-binding gs://based-hardware-dev-agent "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=roles/storage.objectViewer --condition=None"
    ) in commands
    assert (
        "iam service-accounts add-iam-policy-binding "
        "omi-agent-vm-bootstrap@based-hardware-dev.iam.gserviceaccount.com "
        "--project=based-hardware-dev "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=roles/iam.serviceAccountUser --condition=None"
    ) in commands

    legacy_upgrade = subprocess.run(
        ["bash", "backend/scripts/apply-agent-vm-reconciler-iam.sh"],
        cwd=REPO_DIR,
        env={
            **base_env,
            "AGENT_VM_RECONCILER_DEPLOYER": "local-development-joan@based-hardware-dev.iam.gserviceaccount.com",
            "FAKE_GCLOUD_LEGACY_DISK_BINDING": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert legacy_upgrade.returncode == 0, legacy_upgrade.stderr
    upgraded_commands = command_log.read_text(encoding="utf-8")
    assert (
        "projects remove-iam-policy-binding based-hardware-dev "
        "--member=serviceAccount:agent-vm-reconciler@based-hardware-dev.iam.gserviceaccount.com "
        "--role=projects/based-hardware-dev/roles/omiAgentVmReconciler "
        "--condition=title=Agent VM reconciler disk scope,description=Boot disk reads for omi-agent instances "
        "in the Agent VM zone,expression=resource.type == 'compute.googleapis.com/Disk' && "
        "resource.name.startsWith('projects/based-hardware-dev/zones/us-central1-a/disks/omi-agent-')"
    ) in upgraded_commands


def test_reconciler_runbook_documents_state_disk_clone_browser_and_production_gates():
    runbook = _read("docs/runbooks/agent-vm-fleet-reconciler.md")

    assert "persistent state disk" in runbook
    assert "source clone" in runbook
    assert "explicit ephemeral browser policy" in runbook
    assert "autoDelete: true" in runbook
    assert "temporary clone" in runbook
    assert "identity-fenced cleanup" in runbook
    assert "seven days of rollback retention" in runbook
    assert "production canary must communicate that expected" in runbook
    assert "It is not permission for a fleet sweep" in runbook


def test_dev_migration_activation_refuses_by_default_and_uses_generation_guard(tmp_path):
    script = BACKEND_DIR / "scripts" / "activate-agent-vm-dev-migration.sh"
    text = script.read_text(encoding="utf-8")
    assert 'AGENT_VM_MIGRATION_APPLY:-}' in text
    assert 'project" != "based-hardware-dev"' in text
    assert "gcloud storage cp --no-clobber" in text
    assert "--if-generation-match" in text
    assert "--cache-control='no-store,max-age=0'" in text
    assert "cmp -s" in text

    refused = subprocess.run(["bash", str(script)], cwd=REPO_DIR, text=True, capture_output=True, check=False)
    assert refused.returncode == 1
    assert "REFUSED:" in refused.stderr


def test_dev_migration_activation_verifies_bucket_project_and_previous_snapshot():
    script = BACKEND_DIR / "scripts" / "activate-agent-vm-dev-migration.sh"
    text = script.read_text(encoding="utf-8")
    assert "gcloud projects describe" in text
    assert "https://storage.googleapis.com/storage/v1/b/" in text
    assert "projectNumber" in text
    assert "refusing cross-environment activation" in text
    assert "previous.json" in text
    assert "rollback" in text or "Snapshot" in text or "snapshot" in text
    assert "uid.strip()" in text


def test_revoke_script_removes_all_conditional_bindings_and_verifies_absence():
    script = _read("backend/scripts/revoke-agent-vm-bootstrap-stop.sh")

    assert "--all" in script
    assert "get-iam-policy" in script
    assert "binding remains" in script
    assert "|| true" not in script
