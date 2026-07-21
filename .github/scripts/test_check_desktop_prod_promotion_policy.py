from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).with_name("check-desktop-prod-promotion-policy.py")
BETA_WORKFLOW = Path(".github/workflows/desktop_promote_beta.yml")


def policy_module():
    spec = importlib.util.spec_from_file_location("check_desktop_prod_promotion_policy", SCRIPT)
    assert spec is not None and spec.loader is not None
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    return policy


def beta_workflow() -> str:
    return BETA_WORKFLOW.read_text(encoding="utf-8")


def test_policy_validation_runs_without_site_packages():
    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPT)],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_beta_policy_requires_nonautomatic_dispatch_rejection_before_promotion_steps():
    without_rejection = beta_workflow().replace(
        '''      - name: Reject nonautomatic beta request
        env:
          AUTOMATIC: ${{ inputs.automatic }}
        run: |
          set -euo pipefail
          if [[ "${AUTOMATIC,,}" != "true" ]]; then
            echo "Beta promotion only accepts trusted automatic=true qualification handoffs." >&2
            exit 1
          fi

''',
        "",
        1,
    )

    errors = policy_module().validate_beta(without_rejection)

    assert any("reject workflow_dispatch automatic=false before promotion" in error for error in errors)


def test_beta_policy_rejects_dynamic_job_environment_hidden_by_beta_comment():
    dynamic_environment = beta_workflow().replace(
        "environment: beta",
        "# environment: beta\n    environment: ${{ inputs.target_environment }}",
        1,
    )

    errors = policy_module().validate_beta(dynamic_environment)

    assert any("literal jobs.promote.environment: beta" in error for error in errors)


def test_beta_policy_uses_the_actual_job_environment_not_comment_text():
    beta_with_prod_comment = beta_workflow().replace(
        "environment: beta",
        "# environment: prod\n    environment: beta",
        1,
    )

    assert policy_module().validate_beta(beta_with_prod_comment) == []
