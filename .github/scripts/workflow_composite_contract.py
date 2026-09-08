"""Shared helpers for expanding composite actions into workflow contract checks."""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY_BACKEND_STACK_ACTION_REF = "./.github/actions/deploy-backend-stack"
DEPLOY_BACKEND_STACK_USES_MARKER = f"uses: {DEPLOY_BACKEND_STACK_ACTION_REF}"
_DEPLOY_BACKEND_STACK_USES_LINE = re.compile(
    rf"^\s*uses:\s*{re.escape(DEPLOY_BACKEND_STACK_ACTION_REF)}\s*(?:#.*)?$"
)


def line_has_active_deploy_backend_stack_uses(line: str) -> bool:
    """Return whether a workflow line is an active deploy-backend-stack uses step."""

    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    return _DEPLOY_BACKEND_STACK_USES_LINE.fullmatch(line) is not None


def workflow_text_has_active_deploy_backend_stack_uses(text: str) -> bool:
    return any(line_has_active_deploy_backend_stack_uses(line) for line in text.splitlines())


def block_has_active_deploy_backend_stack_uses(block: list[str]) -> bool:
    return any(line_has_active_deploy_backend_stack_uses(line) for line in block)


def composite_action_step_lines(action_text: str) -> list[str]:
    """Return composite-action step lines with workflow-style indentation."""

    lines = action_text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == "  steps:")
    except StopIteration:
        return []

    step_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("    - "):
            step_lines.append(f"      - {line[6:]}")
        elif line.startswith("      "):
            step_lines.append(f"      {line[6:]}")
        elif line.strip() == "":
            continue
        elif not line.startswith(" "):
            break
        elif line.startswith("  ") and not line.startswith("    "):
            break
    return step_lines


def expand_text_at_active_deploy_backend_stack_uses(text: str, expansion: str) -> str:
    """Replace each active deploy-backend-stack uses line with ``expansion``."""

    expansion_lines = expansion.splitlines()
    result: list[str] = []
    for line in text.splitlines():
        if line_has_active_deploy_backend_stack_uses(line):
            result.extend(expansion_lines)
            continue
        result.append(line)
    return "\n".join(result)


def expand_deploy_job_block_at_active_uses(deploy_block: list[str], action_text: str) -> str:
    """Expand a deploy job block by substituting composite steps at the active uses line."""

    composite_lines = composite_action_step_lines(action_text)
    expanded: list[str] = []
    for line in deploy_block:
        if line_has_active_deploy_backend_stack_uses(line):
            expanded.extend(composite_lines)
            continue
        expanded.append(line)
    return "\n".join(expanded)


def backend_deploy_contract_text(
    workflow_text: str,
    root: Path,
    action_relative: Path,
) -> str:
    """Return workflow text expanded with the composite action when it is actively used."""

    if not workflow_text_has_active_deploy_backend_stack_uses(workflow_text):
        return workflow_text
    action_path = root / action_relative
    if not action_path.is_file():
        return workflow_text
    action_text = action_path.read_text(encoding="utf-8")
    return expand_text_at_active_deploy_backend_stack_uses(workflow_text, action_text)
