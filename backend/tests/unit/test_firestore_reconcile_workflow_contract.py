"""Static tripwire for the Firestore reconcile cron's billing-query contract.

Label: static checker, not behavioral coverage. It pins the decision that the
billed-read query goes through the BigQuery REST API with a token minted from
the ambient credential — NOT through the `bq` CLI, which is unusable from a
federated CI identity (it ignores GOOGLE_APPLICATION_CREDENTIALS and enters a
first-run account prompt that non-TTY runners abort;
FC-bq-federated-quota-project, six dispatches burned 2026-10-07). The
reconcile script's own unit tests cover outcome logic; this file only guards
the invocation shape against silent regression to the CLI.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "backend/scripts/firestore_read_reconcile.py"


def test_billing_query_uses_rest_not_bq_cli():
    text = SCRIPT.read_text()
    assert "bigquery.googleapis.com" in text, (
        "the billed-read fetch must call the BigQuery REST jobs.query endpoint; "
        "the bq CLI cannot authenticate from a federated CI identity without an "
        "interactive account layer"
    )
    assert '"bq",' not in text, (
        "a bq CLI invocation regressed into the script; it enters the first-run "
        "account prompt on non-TTY runners and exits 1 before inserting any job"
    )
    assert '"print-access-token"' in text, "the REST call needs a token minted from the ambient credential"


def test_billing_query_failures_surface_response_body():
    text = SCRIPT.read_text()
    assert "billing query failed: HTTP" in text, (
        "an HTTPError must carry the response body into the raised error; a " "swallowed denial cost six CI dispatches"
    )
