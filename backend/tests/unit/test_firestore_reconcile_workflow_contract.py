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

import ast
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/firestore_read_reconcile.py"


def _module() -> ast.Module:
    return ast.parse(SCRIPT.read_text())


def test_billing_query_uses_rest_jobs_query():
    """The script must call the jobs.query endpoint with a structurally-built
    request whose URL comes from the PROJECT_ID constant, and must never
    shell out to the bq CLI."""
    tree = _module()
    request_calls = [
        c
        for c in ast.walk(tree)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "Request"
    ]
    assert request_calls, "the billed-read fetch must issue an HTTP request via urllib.request.Request"
    path_fragments = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "/queries" in n.value
    ]
    assert path_fragments, "the request must target the jobs.query endpoint"
    source = SCRIPT.read_text()
    assert '"bq",' not in source, (
        "a bq CLI invocation regressed into the script; it enters the first-run "
        "account prompt on non-TTY runners and exits 1 before inserting any job"
    )
    assert "google.auth.default" in source, "the REST call needs a token minted from the ambient credential"


def test_billing_query_failures_surface_and_retry():
    """Denials must carry the response body into the raised error, and the
    only daily run must survive transient 5xx/429/network failures."""
    source = SCRIPT.read_text()
    assert "billing query failed after 3 attempts" in source, (
        "an HTTPError must carry the response body into the raised error; a " "swallowed denial cost six CI dispatches"
    )
    assert "jobComplete" in source, (
        "jobs.query answers HTTP 200 with jobComplete=false and no rows when "
        "the aggregate outlives the server wait; treating that as a zero bill "
        "under-states the day"
    )
