from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".." / ".github" / "workflows" / "jit_qa_manual_operator.yml"


def test_manual_operator_is_main_only_and_qa_fenced():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "based-hardware-dev" in text
    assert "QA_DATABASE: jit-qa" in text
    assert "QA_UID: vi7SA9ckQCe4ccobWNxlbdcNdC23" in text
    assert "QA_DRAIN_JOB: knowledge-ledger-drain-qa-job" in text
    assert "source_sha" in text
    assert "verify_backend_release_admission.py" in text
    assert "actions/upload-artifact@v7" in text


def test_manual_operator_uses_existing_seed_contract_without_deploying_resources():
    text = WORKFLOW.read_text(encoding="utf-8")
    for operation in ("bootstrap", "prepare", "inspect", "drain-verify", "rollback"):
        assert operation in text
    assert "jit_qa_seed_and_verify.py bootstrap" in text
    assert "jit_qa_seed_and_verify.py" in text
    assert "--update-env-vars \"KNOWLEDGE_LEDGER_DRAIN_ENABLED=true" in text
    assert "jobs executions describe" in text
    assert "jit_qa_manual_operator.py validate-job" in text
    assert "DRAIN_VERIFY_QA" in text
    assert "ROLLBACK_QA" in text
    assert "gcloud run deploy" not in text
    assert "gcloud run jobs deploy" not in text
    assert "gcloud scheduler" not in text
    assert "docker build" not in text
    assert "api.omi.me" not in text
