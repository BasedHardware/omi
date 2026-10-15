#!/usr/bin/env python3
"""Contract tests for stale-main auto-deploy exits and downstream step gates."""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/gcp_daily_memory_sweep_job.yml",
    ".github/workflows/gcp_daily_memory_sweep_job_auto_dev.yml",
    ".github/workflows/gcp_day3_reengagement_email_job.yml",
    ".github/workflows/gcp_day3_reengagement_email_job_auto_dev.yml",
)


def test_every_main_advanced_branch_is_neutral_and_gates_later_steps():
    branch_count = 0
    for relative_path in WORKFLOWS:
        path = ROOT / relative_path
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        jobs = workflow["jobs"]
        assert len(jobs) == 1, relative_path
        steps = next(iter(jobs.values()))["steps"]
        prior_checks = []
        for index, step in enumerate(steps):
            condition = step.get("if", "")
            for check_id in prior_checks:
                assert f"steps.{check_id}.outputs.superseded != 'true'" in condition, (
                    relative_path,
                    step.get("name"),
                    check_id,
                )

            run = step.get("run", "")
            if "main advanced to ${" not in run:
                continue
            branch_count += 1
            check_id = step.get("id")
            assert check_id, (relative_path, step.get("name"))
            assert 'echo "superseded=true" >> "$GITHUB_OUTPUT"' in run
            assert "::notice title=Superseded::main advanced to ${" in run
            assert 'a newer run deploys it' in run
            branch = re.search(
                r'if \[\[ "\$(?:current_main_sha|DEPLOY_SHA)" != "\$(?:ADMITTED_SHA|main_sha)" \]\]; then\n'
                r'(.*?)\n\s*fi',
                run,
                flags=re.DOTALL,
            )
            assert branch is not None, (relative_path, step.get("name"))
            assert "exit 0" in branch.group(1)
            assert "exit 1" not in branch.group(1)
            prior_checks.append(check_id)

    assert branch_count == 10


if __name__ == "__main__":
    test_every_main_advanced_branch_is_neutral_and_gates_later_steps()
    print("superseded auto-deploy workflow contracts passed")
