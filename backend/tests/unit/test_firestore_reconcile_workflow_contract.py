"""Static tripwire for the Firestore reconcile cron's bq invocation contract.

Label: static checker, not behavioral coverage. It pins the two flags that a
federated-CI (WIF) `bq` invocation needs — `--headless` and a credentialed
gcloud account layer — because losing either re-enters the first-run prompt
that non-TTY runners abort (FC-bq-federated-quota-project, six dispatches
burned 2026-10-07). The reconcile script's own unit tests cover outcome logic;
this file only guards the invocation shape against silent regression.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github/workflows/firestore_read_reconcile.yml"
SCRIPT = REPO_ROOT / "backend/scripts/firestore_read_reconcile.py"


def test_workflow_credentials_the_gcloud_account_layer_with_force():
    text = WORKFLOW.read_text()
    assert "gcloud auth login --cred-file" in text, (
        "bq ignores GOOGLE_APPLICATION_CREDENTIALS; the reconcile workflow must "
        "authorize a gcloud account from the WIF-minted credential file before "
        "the reconcile step"
    )
    assert "--force" in text, (
        "auth@v3 pre-registers the service account, so the login prompts "
        "'overwrite existing credentials?' and a non-TTY runner aborts without "
        "--force"
    )


def test_reconcile_script_invokes_bq_headless():
    text = SCRIPT.read_text()
    assert '"bq"' in text and '"query"' in text
    assert '"--headless"' in text, (
        "without --headless, bq's first-run onboarding prompt exits 1 on a " "non-TTY runner before any job is inserted"
    )
    assert '"--project_id=based-hardware"' in text, (
        "the billing project follows --project_id; a missing project selector "
        "sends the job to the wrong quota context"
    )
