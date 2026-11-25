#!/usr/bin/env python3
"""Inventory direct prod writers and require checked-out main source identity."""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import re

import yaml

WORKFLOWS = (
    Path(".github/workflows/gcp_backend_listen_helm.yml"),
    Path(".github/workflows/gcp_backend_pusher.yml"),
    Path(".github/workflows/gcp_llm_gateway.yml"),
)
CHECKOUT = "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}"
PUSHER_WORKFLOW = Path(".github/workflows/gcp_backend_pusher.yml")
PUSHER_CHECKOUT = (
    "ref: ${{ github.event.inputs.environment == 'prod' && github.workflow_sha || github.event.inputs.branch }}"
)
ORIGIN_MAIN_FETCH = "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main"
ANCESTRY_GUARD = 'git merge-base --is-ancestor "$CHECKED_OUT_SHA" origin/main'
HEAD_IDENTITY = "CHECKED_OUT_SHA=$(git rev-parse HEAD)"
IMAGE_IDENTITY = 'IMAGE_TAG=$(git rev-parse --short=7 "$CHECKED_OUT_SHA")'
DIAGNOSTIC = "ERROR: checked-out HEAD $CHECKED_OUT_SHA is not an ancestor of fresh origin/main"
PERSISTED_IMAGE_IDENTITY = 'echo "IMAGE_TAG=$IMAGE_TAG" >> "$GITHUB_ENV"'
CONTROL_CHECKOUT = (
    "uses: actions/checkout@v7\n"
    "        with:\n"
    "          ref: ${{ github.workflow_sha }}\n"
    "          path: .github/firestore-workflow\n"
    "          persist-credentials: false"
)
GATEWAY_WORKFLOW = Path(".github/workflows/gcp_llm_gateway.yml")
LISTEN_WORKFLOW = Path(".github/workflows/gcp_backend_listen_helm.yml")
LISTEN_PINNED_CHECKOUT = (
    "ref: ${{ inputs.control_sha != '' && github.sha || "
    "(inputs.mode == 'evidence' && inputs.expected_sha || "
    "(github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch)) }}"
)
LISTEN_EXACT_CONTROL_STEP = """name: Verify exact listen control SHA
        if: ${{ inputs.control_sha != '' }}
        shell: bash
        env:
          CONTROL_SHA: ${{ inputs.control_sha }}
          DEPLOY_ENV: ${{ inputs.environment }}
          DEPLOY_MODE: ${{ inputs.mode }}
        run: |
          set -euo pipefail
          if [[ "$GITHUB_EVENT_NAME" != workflow_dispatch || "$DEPLOY_ENV" != prod || "$DEPLOY_MODE" != deploy ||
                ! "$CONTROL_SHA" =~ ^[0-9a-f]{40}$ || "$CONTROL_SHA" == 0000000000000000000000000000000000000000 ||
                "$CONTROL_SHA" != "$GITHUB_SHA" || "$CONTROL_SHA" != "$(git rev-parse HEAD)" ]]; then
            echo "::error title=Listen control mismatch::The production workflow and checkout must match the admitted control SHA."
            exit 1
          fi"""
LISTEN_LEGACY_ANCESTRY = 'if ! git merge-base --is-ancestor "$EXPECTED_SHA" "$CHECKED_OUT_SHA"; then'
LISTEN_EVIDENCE_CONTROL = CONTROL_CHECKOUT.replace('.github/firestore-workflow', '.github/listen-evidence-control')
LISTEN_EXPORTER_CHECKOUT = "ref: ${{ needs.helm-upgrade.outputs.checked_out_sha }}"
GATEWAY_RELEASE_SHA_INPUT = (
    "      release_sha:\n"
    "        description: 'Production only: exact main SHA with a successful first-attempt Release Eligibility proof'\n"
    "        required: false\n"
    "        default: ''"
)


def validate_listen_control_admission(text: str) -> list[str]:
    """Require the pinned checkout and blocking guard before any deploy steps."""
    trigger, _, helm_job = text.partition("\n  helm-upgrade:\n")
    helm_job = helm_job.partition("\n  deploy-neg-coverage-exporter:\n")[0]
    steps = re.split(r"(?m)^      - ", helm_job.partition("\n    steps:\n")[2])[1:]
    # Accept the same exact checkout action pin that the real-step inventory admits.
    if len(steps) >= 2:
        steps[1] = re.sub(r'(?m)^        uses: actions/checkout@' + CHECKOUT_PIN + r'(?: # v7)?$',
                          '        uses: actions/checkout@v7', steps[1])
    checkout = (
        "name: Checkout\n"
        "        uses: actions/checkout@v7\n"
        "        with:\n"
        f"          {LISTEN_PINNED_CHECKOUT}\n"
        "          fetch-depth: 0"
    )
    errors = []
    if not re.search(
        r"(?m)^      control_sha:\n        description: [^\n]+\n"
        r"        required: false\n        default: ''\n        type: string$",
        trigger,
    ):
        errors.append(f"{LISTEN_WORKFLOW} must expose the optional control_sha string input")
    if (
        len(steps) < 3
        or not steps[0].startswith("name: Validate Environment Input\n")
        or steps[1].rstrip() != checkout
        or steps[2].rstrip() != LISTEN_EXACT_CONTROL_STEP
    ):
        errors.append(f"{LISTEN_WORKFLOW} must pin the dispatch checkout and verify exact control before deployment")
    if LISTEN_LEGACY_ANCESTRY not in helm_job:
        errors.append(f"{LISTEN_WORKFLOW} must retain expected_sha containment for legacy admission")
    return errors


def validate_gateway_release_admission(text: str) -> list[str]:
    """Require the standalone gateway's production SHA to use the shared proof gate."""

    errors: list[str] = []
    for fragment, message in (
        (GATEWAY_RELEASE_SHA_INPUT, "gateway deploy must expose a production-only release_sha input"),
        (
            "ref: ${{ github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch }}",
            "gateway development deploy must retain its branch checkout while production starts from main",
        ),
        (
            "sha_pattern='^[0-9a-f]{40}$'",
            "gateway production admission must reject malformed or missing release_sha",
        ),
        (
            '[[ ! "$DEPLOY_SHA" =~ $sha_pattern || "$DEPLOY_SHA" == "0000000000000000000000000000000000000000" ]]',
            "gateway production admission must reject malformed or missing release_sha",
        ),
        (
            'git cat-file -e "${DEPLOY_SHA}^{commit}"',
            "gateway production admission must require the requested SHA commit object",
        ),
        (
            'git merge-base --is-ancestor "$DEPLOY_SHA" "$main_sha"',
            "gateway production admission must require release_sha to be merged into fresh main",
        ),
        (
            "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=completed&head_sha=${DEPLOY_SHA}",
            "gateway production admission must query Release Eligibility for the exact SHA",
        ),
        (
            ".github/scripts/verify_backend_release_admission.py",
            "gateway production admission must verify the Release Eligibility proof",
        ),
        (
            "--require-first-attempt",
            "gateway production admission must reject Release Eligibility reruns",
        ),
        (
            'git checkout --detach "$DEPLOY_SHA"',
            "gateway production admission must check out the admitted SHA",
        ),
        (
            '"$CHECKED_OUT_SHA" != "$DEPLOY_SHA"',
            "gateway production admission must bind image identity to the admitted checkout",
        ),
    ):
        if fragment not in text:
            errors.append(message)
    return errors


def validate_gateway_break_glass_hatch(text: str) -> list[str]:
    """Pin the gateway eligibility-proof break-glass hatch properties.

    Every gated surface must have a break-glass hatch (AGENTS.md). The hatch
    may skip the eligibility proof, never the ancestry check, and its use must
    be recorded as a tracking issue. These are static tripwires, not behavioral
    coverage.
    """

    errors: list[str] = []
    for fragment, message in (
        (
            "skip_eligibility_proof:\n        description: 'Break-glass: deploy without a Release Eligibility proof (still requires a merged main SHA)'",
            "gateway deploy must expose a skip_eligibility_proof break-glass input",
        ),
        (
            '!= "deploy-without-proof"',
            "gateway break-glass must require an explicit confirm string",
        ),
        (
            "requires a non-empty break_glass_reason",
            "gateway break-glass must require a non-empty reason",
        ),
        (
            'record_break_glass:',
            "gateway break-glass use must be recorded by a dedicated job",
        ),
        (
            "--label release-gate-failure",
            "gateway break-glass tracking issue must carry the release-gate-failure label",
        ),
    ):
        if fragment not in text:
            errors.append(message)
    return errors


# Closed recognition only: the rollout lead approved this exact checkout pin.
CHECKOUT_PIN = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
CHECKOUT_ACTIONS = {"actions/checkout@v7", "actions/checkout@" + CHECKOUT_PIN}


@lru_cache(maxsize=8)
def workflow_steps(text: str) -> list[dict]:
    """Read real job step mappings with the repository's existing YAML loader.

    Reject aliases and duplicate keys rather than letting scalar text or a
    second interpretation supply admission authority. No workflow is executed.
    """
    if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
        raise ValueError("aliased workflow source")
    root = yaml.compose(text, Loader=yaml.BaseLoader)

    def mapping(node):
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("expected workflow mapping")
        result = {}
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.value in result:
                raise ValueError("ambiguous workflow key")
            result[key.value] = value
        return result

    def scalar(node):
        if not isinstance(node, yaml.ScalarNode):
            raise ValueError("expected step scalar")
        return node.value

    jobs = mapping(mapping(root)['jobs'])
    steps = []
    for job_name, job in jobs.items():
        job = mapping(job)
        if 'steps' not in job:
            continue
        sequence = job['steps']
        if not isinstance(sequence, yaml.SequenceNode):
            raise ValueError("expected workflow steps")
        for index, node in enumerate(sequence.value):
            step = mapping(node)
            if 'job' in step or 'index' in step:
                raise ValueError('reserved step field')
            values = {'job': job_name, 'index': index}
            for key, value in step.items():
                values[key] = mapping(value) if key in ('with', 'env') else scalar(value)
            for key in ('with', 'env'):
                if key in values:
                    values[key] = {name: scalar(value) for name, value in values[key].items()}
            steps.append(values)
    return steps


def checkout_inventory(text: str) -> tuple[str, int, bool]:
    steps = workflow_steps(text)
    checkouts = [step['uses'] for step in steps if re.search(r'(?:^|/)checkout(?:@|$)', step.get('uses', '').lower())]
    # Normalization is only for retained legacy text guards; counts and
    # exemptions below derive exclusively from actual YAML step mappings.
    normalized = text.replace('actions/checkout@' + CHECKOUT_PIN, 'actions/checkout@v7')
    return normalized, len(checkouts), any(value not in CHECKOUT_ACTIONS for value in checkouts)


def isolated_checkout_count(text: str, contract: str) -> int:
    target = (
        '.github/listen-evidence-control' if 'listen-evidence-control' in contract else '.github/firestore-workflow'
    )
    return sum(
        step.get('uses') in CHECKOUT_ACTIONS
        and step.get('with', {}).get('ref') == '${{ github.workflow_sha }}'
        and step.get('with', {}).get('path') == target
        and step.get('with', {}).get('persist-credentials') == 'false'
        for step in workflow_steps(text)
    )


BOOTSTRAP_RUN = 'python3 .github/listen-evidence-control/.github/scripts/listen_runtime.py reconstruct --root "$RUNNER_TEMP/listen-runtime"\necho "$RUNNER_TEMP/listen-runtime/helm/linux-amd64" >> "$GITHUB_PATH"\n'


PRODUCER_RUN = 'set -euo pipefail\numask 077\nexport LD_LIBRARY_PATH="$RUNNER_TEMP/listen-runtime/python/lib"\nunset LD_PRELOAD PYTHONHOME PYTHONPATH\n"$RUNNER_TEMP/listen-runtime/python/bin/python3.12" -I -B .github/listen-evidence-control/.github/scripts/listen_overlay_evidence.py job \\\n  --root "$GITHUB_WORKSPACE" --output "$RUNNER_TEMP/listen-overlay-receipt.json"\n'


def evidence_commands_bound(text: str) -> bool:
    steps = workflow_steps(text)
    controls = [step for step in steps if step.get('with', {}).get('path') == '.github/listen-evidence-control']
    if (
        len(controls) != 1
        or controls[0]['job'] != 'helm-upgrade'
        or controls[0].get('if') != "${{ inputs.mode == 'evidence' }}"
    ):
        return False
    expected = {
        'Reconstruct evidence runtime before credentials': BOOTSTRAP_RUN,
        'Produce private-overlay effect receipt without mutation': PRODUCER_RUN,
    }
    indices = [controls[0]['index']]
    for name, run in expected.items():
        matches = [step for step in steps if step.get('name') == name]
        if len(matches) != 1:
            return False
        step = matches[0]
        if (
            step['job'] != 'helm-upgrade'
            or step.get('run') != run
            or step.get('if') != "${{ inputs.mode == 'evidence' }}"
            or any(key in step for key in ('uses', 'working-directory', 'shell', 'continue-on-error'))
        ):
            return False
        expected_env = (
            {}
            if name.startswith('Reconstruct')
            else {
                'EVIDENCE_REQUEST': '${{ inputs.evidence_request }}',
                'LISTEN_PRIVATE_VALUES_YAML': '${{ secrets.LISTEN_PRIVATE_VALUES_YAML }}',
            }
        )
        if step.get('env', {}) != expected_env:
            return False
        indices.append(step['index'])
    return indices == sorted(set(indices))


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in WORKFLOWS:
        path = root / relative
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        expected_checkout = PUSHER_CHECKOUT if relative == PUSHER_WORKFLOW else CHECKOUT
        if relative == LISTEN_WORKFLOW:
            errors.extend(validate_listen_control_admission(text))
        elif expected_checkout not in text:
            errors.append(f"{relative} must reject caller refs for production checkout")
        if ORIGIN_MAIN_FETCH not in text or ANCESTRY_GUARD not in text:
            errors.append(f"{relative} must prove production source is on fresh origin/main")
        if HEAD_IDENTITY not in text or IMAGE_IDENTITY not in text:
            errors.append(f"{relative} must derive image identity from checked-out HEAD")
        if DIAGNOSTIC not in text:
            errors.append(f"{relative} must diagnose a rejected checked-out source identity")
        if "${GITHUB_SHA::7}" in text:
            errors.append(f"{relative} must not label built source with GITHUB_SHA")
        try:
            checkout_text, checkout_count, unknown_checkout = checkout_inventory(text)
            firestore_controls = isolated_checkout_count(checkout_text, CONTROL_CHECKOUT)
            evidence_controls = isolated_checkout_count(checkout_text, LISTEN_EVIDENCE_CONTROL)
            commands_bound = evidence_commands_bound(text) if relative == LISTEN_WORKFLOW else True
        except (ValueError, KeyError, TypeError, yaml.YAMLError):
            errors.append(f"{relative} must have unambiguous real workflow steps")
            checkout_count, unknown_checkout = -100, True
            firestore_controls = evidence_controls = 0
            commands_bound = False
        if unknown_checkout:
            errors.append(f"{relative} has an unapproved checkout action or version")
        source_checkouts = checkout_count - firestore_controls
        if relative == LISTEN_WORKFLOW:
            # A separate immutable control checkout is not an application source.
            # Recognize only the exact path/ref/nonpersistent-credentials contract.
            source_checkouts -= evidence_controls
            if evidence_controls != 1:
                errors.append(f"{relative} evidence controls must use immutable workflow source in their isolated path")
            if not commands_bound:
                errors.append(f"{relative} evidence commands must execute isolated immutable controls in order")
        expected_checkouts = 2 if relative == LISTEN_WORKFLOW else 1
        if source_checkouts != expected_checkouts:
            errors.append(f"{relative} must not check out a second source after production admission")
        if relative == LISTEN_WORKFLOW and LISTEN_EXPORTER_CHECKOUT not in text:
            errors.append(f"{relative} exporter job must check out the exact source admitted by helm-upgrade")
        if text.count(HEAD_IDENTITY) != 1:
            errors.append(f"{relative} must establish checked-out source identity exactly once")
        persistent_image_writes = [
            line.strip()
            for line in re.findall(r"(?m)^[^\n]*\bIMAGE_TAG=[^\n]*>>\s*[\"']?\$GITHUB_ENV[\"']?[^\n]*$", text)
        ]
        image_authorities = []
        for line in text.splitlines():
            assignment = re.match(r"^\s*(?:run:\s+)?IMAGE_TAG=(.*)$", line)
            if assignment and not re.match(r"[\"']?\$\{?IMAGE_TAG\}?\b", assignment.group(1)):
                image_authorities.append(line.strip())
        if (
            text.count(IMAGE_IDENTITY) != 1
            or image_authorities != [IMAGE_IDENTITY]
            or persistent_image_writes != [PERSISTED_IMAGE_IDENTITY]
        ):
            errors.append(f"{relative} must establish its immutable image tag exactly once from checked-out HEAD")
        if relative == GATEWAY_WORKFLOW:
            errors.extend(validate_gateway_release_admission(text))
            errors.extend(validate_gateway_break_glass_hatch(text))
        if relative == PUSHER_WORKFLOW:
            for fragment in (
                '"$GITHUB_REF" != refs/heads/main || "$GITHUB_SHA" != "$WORKFLOW_CONTROL_SHA"',
                'BRANCH_INPUT: ${{ github.event.inputs.branch }}',
                'if [[ "$BRANCH_INPUT" == main ]]; then',
                'PINNED_PUSHER_RELEASE_SHA=\'\'',
                '[[ ! "$BRANCH_INPUT" =~ ^[0-9a-f]{40}$ || "$BRANCH_INPUT" == "0000000000000000000000000000000000000000" ]]',
                'backend/scripts/verify_pusher_promotion_evidence.py --admit-source',
                '--release-sha "$PINNED_PUSHER_RELEASE_SHA" --workflow-sha "$WORKFLOW_CONTROL_SHA"',
                'if [[ -n "$PINNED_PUSHER_RELEASE_SHA" ]]; then',
                'actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=completed&head_sha=${DEPLOY_SHA}',
                '.github/scripts/verify_backend_release_admission.py',
                '--workflow-runs "$PROOF" --require-first-attempt',
                'git checkout --detach "$DEPLOY_SHA"',
                '"$CHECKED_OUT_SHA" != "$DEPLOY_SHA"',
                'echo "PINNED_PUSHER_RELEASE_SHA=$PINNED_PUSHER_RELEASE_SHA" >> "$GITHUB_ENV"',
                '--expected-qualification-source-sha "$PINNED_PUSHER_RELEASE_SHA"',
            ):
                if fragment not in text:
                    errors.append(f"{relative} is missing trusted pinned-source admission: {fragment}")
            if text.count('--expected-canary-workflow-sha "$GITHUB_SHA"') != 2:
                errors.append(f"{relative} must bind canary and final run identity to trusted GITHUB_SHA")
    return errors


if __name__ == "__main__":
    raise SystemExit(1 if validate(Path(".")) else 0)
