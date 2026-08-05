import importlib.util
from pathlib import Path

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


def test_desktop_workflows_guard_active_pointer_reads_writes_and_cleanup_rollbacks():
    for workflow in ("desktop_backend_auto_dev.yml", "desktop_backend_prod.yml"):
        text = _read(f".github/workflows/{workflow}")

        assert "gcloud storage objects describe" in text
        assert "NOT_FOUND" in text
        assert "--if-generation-match" in text
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
    assert "validate_agent_vm_reconciler_scheduler.py" in script
    assert "--scheduler-service-account \"$scheduler_sa\"" in script


def test_reconciler_iam_installer_refuses_by_default_and_keeps_bindings_scoped():
    script = _read("backend/scripts/apply-agent-vm-reconciler-iam.sh")

    assert 'AGENT_VM_RECONCILER_IAM_APPLY:-}' in script
    assert "REFUSED:" in script
    assert (
        "compute.disks.get,compute.instances.get,compute.instances.setMetadata,compute.instances.setServiceAccount,compute.instances.start,compute.instances.stop"
        in script
    )
    assert "Agent VM reconciler instance scope" in script
    assert "Agent VM reconciler disk scope" in script
    assert "compute.googleapis.com/Disk" in script
    assert "disks/omi-agent-" in script
    assert "instances/omi-agent-" in script
    assert "roles/storage.objectViewer" in script
    assert "roles/iam.serviceAccountUser" in script


def test_revoke_script_removes_all_conditional_bindings_and_verifies_absence():
    script = _read("backend/scripts/revoke-agent-vm-bootstrap-stop.sh")

    assert "--all" in script
    assert "get-iam-policy" in script
    assert "binding remains" in script
    assert "|| true" not in script
