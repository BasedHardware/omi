#!/usr/bin/env python3
"""Fail fast on release/process contracts that otherwise break late."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import yaml

from git_bash import bash_executable, bash_path

ROOT = Path(__file__).resolve().parents[2]
MAX_SECURITY_BOUND_FILE_BYTES = 10 * 1024 * 1024


class SecurityBoundFileError(Exception):
    """A release lock input was not read from one verified ordinary file."""


def _security_bound_file_identity(file_stat: os.stat_result) -> tuple[int, int, int]:
    """Return the pathname identity fields that must agree with the descriptor."""
    return file_stat.st_dev, file_stat.st_ino, stat.S_IFMT(file_stat.st_mode)


def _lstat_security_bound_file(path: Path, description: str) -> os.stat_result:
    """Inspect one pathname without following a link and require a regular file."""
    try:
        path_stat = os.lstat(path)
    except OSError as exc:
        raise SecurityBoundFileError(
            f"{description} could not inspect its security-bound file: {path} ({exc})"
        ) from exc
    if not stat.S_ISREG(path_stat.st_mode):
        raise SecurityBoundFileError(
            f"{description} must be an ordinary regular file read without following links: {path}"
        )
    return path_stat


def _read_security_bound_file(path: Path, description: str) -> bytes:
    """Read one bounded ordinary file without following a replacement path.

    The descriptor, not a later pathname lookup, is the source for every
    consumer of this security-bound input. Both pathname checks and descriptor
    checks bind the same ordinary file; O_NOFOLLOW closes the open-time symlink
    race where available, while the identity comparisons keep the fallback
    fail-closed.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
    try:
        before = _lstat_security_bound_file(path, description)
        fd = os.open(path, flags)
    except SecurityBoundFileError:
        raise
    except OSError as exc:
        raise SecurityBoundFileError(
            f"{description} must be an ordinary regular file read without following links: {path} ({exc})"
        ) from exc

    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise SecurityBoundFileError(
                f"{description} must be an ordinary regular file read without following links: {path}"
            )
        if _security_bound_file_identity(before) != _security_bound_file_identity(opened):
            raise SecurityBoundFileError(f"{description} changed while opening its security-bound file: {path}")
        if opened.st_size > MAX_SECURITY_BOUND_FILE_BYTES:
            raise SecurityBoundFileError(f"{description} exceeds the security-bound read limit: {path}")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, MAX_SECURITY_BOUND_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SECURITY_BOUND_FILE_BYTES:
                raise SecurityBoundFileError(f"{description} exceeds the security-bound read limit: {path}")

        completed = os.fstat(fd)
        if (
            *_security_bound_file_identity(opened),
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ) != (
            *_security_bound_file_identity(completed),
            completed.st_size,
            completed.st_mtime_ns,
            completed.st_ctime_ns,
        ):
            raise SecurityBoundFileError(f"{description} changed while being read: {path}")
        final_path_stat = _lstat_security_bound_file(path, description)
        if _security_bound_file_identity(final_path_stat) != _security_bound_file_identity(opened):
            raise SecurityBoundFileError(f"{description} changed while being read: {path}")
        return b"".join(chunks)
    except SecurityBoundFileError:
        raise
    except OSError as exc:
        raise SecurityBoundFileError(f"{description} could not be read safely: {path} ({exc})") from exc
    finally:
        os.close(fd)


def _load_codemagic_with_duplicates(raw_bytes: bytes) -> tuple[dict[str, object], list[str], list[str]]:
    """Load the executable YAML shape; comments never provide release authority."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {}, [], [f"codemagic.yaml must be valid UTF-8: {exc}"]
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        return {}, [], [f"codemagic.yaml is not valid YAML: {exc}"]
    source_errors = _yaml_source_topology_errors(text, root)
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {}, [], [f"codemagic.yaml is not valid YAML: {exc}", *source_errors]
    duplicates: list[str] = []

    def visit(node: yaml.Node | None) -> None:
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key_node, value_node in node.value:
                if isinstance(key_node, yaml.ScalarNode):
                    key = key_node.value
                    if key in keys:
                        duplicates.append(key)
                    keys.add(key)
                visit(value_node)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)

    visit(root)
    if not isinstance(document, dict):
        return {}, duplicates, ["codemagic.yaml must be a mapping", *source_errors]
    return document, duplicates, source_errors


WORKFLOW_CONTRACT_RELATIVE_PATH = Path(".github/scripts/fixtures/codemagic_workflow_contract/v1.json")
CANONICAL_WORKFLOW = "omi-desktop-swift-release"
PREVIEW_WORKFLOW = "omi-desktop-swift-preview"
NORMAL_RELEASE_CREDENTIAL_GROUPS = {"desktop_secrets"}
TEMPORARY_PREVIEW_CREDENTIAL_GROUPS = [
    "desktop_preview_secrets",
    "appstore_credentials",
    "desktop_secrets",
]
WORKFLOW_CONTRACT_SCHEMA_VERSION_FIELD = "schema_version"
WORKFLOW_CONTRACT_SCHEMA_VERSION = 1
CODEMAGIC_RAW_SHA256_FIELD = "codemagic_raw_sha256"
CODEMAGIC_SEMANTIC_SHA256_FIELD = "codemagic_semantic_sha256"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
WORKFLOW_CONTRACT_TOP_LEVEL_KEYS = frozenset(
    {
        WORKFLOW_CONTRACT_SCHEMA_VERSION_FIELD,
        CODEMAGIC_RAW_SHA256_FIELD,
        CODEMAGIC_SEMANTIC_SHA256_FIELD,
        CANONICAL_WORKFLOW,
        PREVIEW_WORKFLOW,
    }
)
WORKFLOW_CONTRACT_NESTED_KEYS = {
    CANONICAL_WORKFLOW: frozenset({"semantic_sha256", "publication_script", "publication_script_sha256"}),
    PREVIEW_WORKFLOW: frozenset({"semantic_sha256"}),
}

# This is deliberately supplemental.  The fixture below is the authority
# boundary; these literals only make obvious new direct authority easy to spot.
_DIRECT_RELEASE_CREATE = re.compile(r"(?m)^\s*gh\s+release\s+create\b")
_DIRECT_GITHUB_RELEASE_API = re.compile(
    r"https://api\.github\.com/repos/[^\s'\"\\]+/releases(?:[/?#]|$)", re.IGNORECASE
)
_FORBIDDEN_NORMAL_RELEASE_GCP_AUTHORITIES = (
    re.compile(r"\bGCP_SERVICE_ACCOUNT_KEY\b"),
    re.compile(r"\bCloud\s+Run\s+Admin\b", re.IGNORECASE),
    re.compile(r"\broles/run\.admin\b", re.IGNORECASE),
    re.compile(r"\bStorage\s+Object\s+Admin\b", re.IGNORECASE),
    re.compile(r"\broles/storage\.objectAdmin\b", re.IGNORECASE),
    re.compile(r"\bGCR\s+push\b", re.IGNORECASE),
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iter_semantic_strings(value: object) -> Iterator[str]:
    """Yield only safely loaded keys and values, deliberately excluding YAML comments."""
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_semantic_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_semantic_strings(child)
    elif isinstance(value, str):
        yield value


class _DuplicateFixtureKeyError(ValueError):
    pass


def _reject_duplicate_fixture_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateFixtureKeyError(key)
        result[key] = value
    return result


def _fixture_sha256_error(field: str) -> str:
    return f"Codemagic workflow contract fixture {field} must be a lowercase SHA-256 digest"


def _load_workflow_contract(raw_bytes: bytes) -> tuple[dict[str, object] | None, list[str]]:
    """Parse the fixture as a closed, typed schema from its verified bytes."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [f"Codemagic workflow contract fixture must be valid UTF-8: {exc}"]
    try:
        contract = json.loads(text, object_pairs_hook=_reject_duplicate_fixture_keys)
    except _DuplicateFixtureKeyError as exc:
        return None, [f"Codemagic workflow contract fixture has duplicate key: {exc}"]
    except json.JSONDecodeError as exc:
        return None, [f"Codemagic workflow contract fixture is invalid JSON: {exc}"]
    if type(contract) is not dict:
        return None, ["Codemagic workflow contract fixture must be a mapping"]
    if set(contract) != WORKFLOW_CONTRACT_TOP_LEVEL_KEYS:
        missing = sorted(WORKFLOW_CONTRACT_TOP_LEVEL_KEYS.difference(contract))
        unknown = sorted(set(contract).difference(WORKFLOW_CONTRACT_TOP_LEVEL_KEYS))
        return None, [
            "Codemagic workflow contract fixture top-level keys must exactly match the approved schema "
            f"(missing: {missing}; unknown: {unknown})"
        ]

    errors: list[str] = []
    schema_version = contract[WORKFLOW_CONTRACT_SCHEMA_VERSION_FIELD]
    if type(schema_version) is not int or schema_version != WORKFLOW_CONTRACT_SCHEMA_VERSION:
        errors.append(
            "Codemagic workflow contract fixture schema_version must be the exact integer "
            f"{WORKFLOW_CONTRACT_SCHEMA_VERSION}"
        )
    for field in (CODEMAGIC_RAW_SHA256_FIELD, CODEMAGIC_SEMANTIC_SHA256_FIELD):
        value = contract[field]
        if type(value) is not str or _SHA256_HEX.fullmatch(value) is None:
            errors.append(_fixture_sha256_error(field))

    for workflow_name, expected_keys in WORKFLOW_CONTRACT_NESTED_KEYS.items():
        workflow = contract[workflow_name]
        if type(workflow) is not dict:
            errors.append(f"Codemagic workflow contract fixture {workflow_name} must be a mapping")
            continue
        if set(workflow) != expected_keys:
            missing = sorted(expected_keys.difference(workflow))
            unknown = sorted(set(workflow).difference(expected_keys))
            errors.append(
                f"Codemagic workflow contract fixture {workflow_name} keys must exactly match the approved schema "
                f"(missing: {missing}; unknown: {unknown})"
            )
            continue
        semantic_digest = workflow["semantic_sha256"]
        if type(semantic_digest) is not str or _SHA256_HEX.fullmatch(semantic_digest) is None:
            errors.append(_fixture_sha256_error(f"{workflow_name}.semantic_sha256"))
        if workflow_name == CANONICAL_WORKFLOW:
            publication_script = workflow["publication_script"]
            publication_digest = workflow["publication_script_sha256"]
            if type(publication_script) is not str:
                errors.append("Codemagic workflow contract fixture publication_script must be an exact string")
            if type(publication_digest) is not str or _SHA256_HEX.fullmatch(publication_digest) is None:
                errors.append(_fixture_sha256_error("publication_script_sha256"))
            elif type(publication_script) is str and _sha256_text(publication_script) != publication_digest:
                errors.append(
                    "Codemagic workflow contract fixture publication script digest does not match publication_script"
                )
    return (contract if not errors else None), errors


def _check_codemagic_document_digest(
    contract: dict[str, object], field: str, actual_digest: str, description: str
) -> list[str]:
    """Require a valid approved digest before narrower Codemagic checks run."""
    expected_digest = contract.get(field)
    if type(expected_digest) is not str or _SHA256_HEX.fullmatch(expected_digest) is None:
        return [_fixture_sha256_error(field)]
    if actual_digest != expected_digest:
        return [f"Codemagic entire document {description} does not match approved fixture {field}"]
    return []


def _yaml_source_topology_errors(text: str, root: yaml.Node | None) -> list[str]:
    """Reject source features that can make a semantic fixture ambiguous."""
    errors: list[str] = []
    try:
        events = list(yaml.parse(text))
    except yaml.YAMLError as exc:
        return [f"codemagic.yaml is not valid YAML: {exc}"]

    anchors = [
        event.anchor
        for event in events
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent, yaml.events.ScalarEvent))
        and event.anchor is not None
    ]
    aliases = [event.anchor for event in events if isinstance(event, yaml.events.AliasEvent)]
    if anchors != ["desktop_signed_artifact_steps"] or aliases != ["desktop_signed_artifact_steps"]:
        errors.append("codemagic.yaml must use exactly the approved desktop_signed_artifact_steps anchor and alias")
    for event in events:
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent, yaml.events.ScalarEvent)):
            if event.tag is not None:
                errors.append("codemagic.yaml must not use explicit YAML tags")
                break

    def visit(node: yaml.Node | None) -> None:
        if isinstance(node, yaml.MappingNode):
            for key_node, value_node in node.value:
                if isinstance(key_node, yaml.ScalarNode) and key_node.value == "<<":
                    errors.append("codemagic.yaml must not use YAML merge keys")
                visit(value_node)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)

    visit(root)
    return errors


def check_codemagic_release_publishers() -> list[str]:
    """Lock the entire Codemagic document and desktop release capability ownership.

    The entire-file raw and safely-loaded semantic digests are the security
    boundary, not regex or credential-name recognition: static analysis cannot
    classify arbitrary Bash or unknown credential capabilities. Future
    Codemagic edits must intentionally update the reviewed fixture digests and
    these regression tests. The narrower workflow, topology, scalar, credential,
    preview, and supplemental checks remain defense in depth.
    """
    codemagic_path = ROOT / "codemagic.yaml"
    try:
        codemagic_bytes = _read_security_bound_file(codemagic_path, "codemagic.yaml")
    except SecurityBoundFileError as exc:
        return [str(exc)]
    raw_digest = _sha256_bytes(codemagic_bytes)
    document, duplicates, errors = _load_codemagic_with_duplicates(codemagic_bytes)
    errors.extend(f"codemagic.yaml has duplicate key: {key}" for key in duplicates)
    workflow_contract = ROOT / WORKFLOW_CONTRACT_RELATIVE_PATH
    try:
        contract_bytes = _read_security_bound_file(workflow_contract, "Codemagic workflow contract fixture")
    except SecurityBoundFileError as exc:
        return [*errors, str(exc)]
    contract, contract_errors = _load_workflow_contract(contract_bytes)
    if contract is None:
        return [*errors, *contract_errors]

    # These comparisons deliberately precede every workflow-specific check.
    # The raw digest includes comments, anchors, aliases, and source topology;
    # the semantic digest independently locks the safely loaded full document.
    errors.extend(_check_codemagic_document_digest(contract, CODEMAGIC_RAW_SHA256_FIELD, raw_digest, "raw byte digest"))
    errors.extend(
        _check_codemagic_document_digest(
            contract,
            CODEMAGIC_SEMANTIC_SHA256_FIELD,
            _sha256_text(_canonical_json(document)),
            "semantic digest",
        )
    )
    workflows = document.get("workflows")
    if not isinstance(workflows, dict):
        return [*errors, "codemagic.yaml is missing its workflows mapping"]
    canonical = workflows.get(CANONICAL_WORKFLOW)
    preview = workflows.get(PREVIEW_WORKFLOW)
    if not isinstance(canonical, dict):
        return [*errors, f"codemagic.yaml is missing the {CANONICAL_WORKFLOW} workflow"]
    if not isinstance(preview, dict):
        return [*errors, f"codemagic.yaml is missing the {PREVIEW_WORKFLOW} workflow"]

    for workflow_name, workflow in ((CANONICAL_WORKFLOW, canonical), (PREVIEW_WORKFLOW, preview)):
        expected = contract.get(workflow_name)
        if not isinstance(expected, dict):
            errors.append(f"Codemagic workflow contract fixture is missing {workflow_name}")
            continue
        actual_digest = _sha256_text(_canonical_json(workflow))
        if actual_digest != expected.get("semantic_sha256"):
            errors.append(f"{workflow_name} semantic workflow contract digest does not match the approved fixture")

    canonical_scripts = canonical.get("scripts")
    preview_scripts = preview.get("scripts")
    if not isinstance(canonical_scripts, list) or not isinstance(preview_scripts, list):
        return [*errors, "canonical and preview workflows must both have scripts"]
    if canonical_scripts is not preview_scripts:
        errors.append("preview scripts must be the exact YAML alias node used by the canonical workflow")
    # 21 approved steps retain the release security boundary while moving the
    # stable/Beta Apple submissions into two identity-labelled parallel batches.
    # The full Beta smoke remains distinct; stable keeps the structural artifact
    # audit without paying for a duplicate launch/auth/notification exercise.
    if len(canonical_scripts) != 21:
        errors.append("canonical workflow must retain exactly 21 approved script steps")

    for scalar in _iter_semantic_strings(canonical):
        for forbidden_authority in _FORBIDDEN_NORMAL_RELEASE_GCP_AUTHORITIES:
            match = forbidden_authority.search(scalar)
            if match is not None:
                errors.append(f"{CANONICAL_WORKFLOW} contains forbidden broad GCP authority {match.group(0)!r}")

    preview_environment = preview.get("environment")
    preview_groups = preview_environment.get("groups") if isinstance(preview_environment, dict) else None
    preview_vars = preview_environment.get("vars") if isinstance(preview_environment, dict) else None
    if preview_groups != TEMPORARY_PREVIEW_CREDENTIAL_GROUPS:
        errors.append(
            "preview workflow must use exactly the approved temporary credential groups "
            f"{TEMPORARY_PREVIEW_CREDENTIAL_GROUPS}"
        )
    if not isinstance(preview_vars, dict) or preview_vars.get("PREVIEW_MODE") != "true":
        errors.append('preview workflow must set exact PREVIEW_MODE: "true"')

    publication_steps = [
        step
        for step in canonical_scripts
        if isinstance(step, dict)
        and step.get("name") == "Create GitHub release"
        and isinstance(step.get("script"), str)
    ]
    if len(publication_steps) != 1:
        errors.append("canonical workflow must contain exactly one Create GitHub release script")
    else:
        publication_script = publication_steps[0]["script"]
        expected_publication = contract.get(CANONICAL_WORKFLOW, {}).get("publication_script")
        if publication_script != expected_publication:
            errors.append("canonical publication script text does not match the approved fixture")
        elif _sha256_text(publication_script) != contract[CANONICAL_WORKFLOW].get("publication_script_sha256"):
            errors.append("canonical publication script digest does not match the approved fixture")
        preview_exit = 'if [[ "${PREVIEW_MODE:-false}" == "true" ]]; then\n  echo "External previews do not create GitHub releases."\n  exit 0\nfi'
        if not publication_script.startswith(preview_exit):
            errors.append("locked preview publication script must exit before reservation or publication")

    for workflow_name, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        environment = workflow.get("environment")
        groups = environment.get("groups", []) if isinstance(environment, dict) else []
        vars_ = environment.get("vars", {}) if isinstance(environment, dict) else {}
        if not isinstance(groups, list):
            errors.append(f"Codemagic workflow {workflow_name} environment groups must be a list")
            continue
        if not isinstance(vars_, dict):
            errors.append(f"Codemagic workflow {workflow_name} environment vars must be a mapping")
            continue
        forbidden_groups = NORMAL_RELEASE_CREDENTIAL_GROUPS.intersection(str(group) for group in groups)
        if workflow_name not in {CANONICAL_WORKFLOW, PREVIEW_WORKFLOW} and forbidden_groups:
            errors.append(
                f"Codemagic workflow {workflow_name} imports normal release credential group(s): {sorted(forbidden_groups)}"
            )
        if workflow_name != CANONICAL_WORKFLOW:
            for token_name in ("GITHUB_TOKEN", "GH_TOKEN"):
                if token_name in vars_:
                    errors.append(f"Codemagic workflow {workflow_name} exposes {token_name} outside canonical release")

    # A deliberately conservative tripwire. It is not used to establish the
    # security boundary; the exact semantic fixture above does that.
    for workflow_name, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        steps = workflow.get("scripts")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("script"), str):
                continue
            script = step["script"]
            approved_shared_publication = workflow_name in {
                CANONICAL_WORKFLOW,
                PREVIEW_WORKFLOW,
            } and script == contract.get(CANONICAL_WORKFLOW, {}).get("publication_script")
            if _DIRECT_RELEASE_CREATE.search(script) and not approved_shared_publication:
                errors.append(
                    f"Codemagic workflow {workflow_name} has direct GitHub release-create authority outside the fixture"
                )
            if _DIRECT_GITHUB_RELEASE_API.search(script):
                errors.append(f"Codemagic workflow {workflow_name} has direct GitHub releases API authority")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(check_desktop_codemagic_release())
    errors.extend(check_desktop_candidate_trigger_authority())
    errors.extend(check_codemagic_release_publishers())
    errors.extend(check_desktop_preview_publishing())
    errors.extend(check_desktop_promotion_independent_of_qualification())
    errors.extend(check_desktop_update_docs())
    errors.extend(check_no_unprovisioned_beta_backend_hosts())
    errors.extend(check_mobile_codemagic_release_triggers())
    errors.extend(check_docs_workflow_scripts())
    errors.extend(check_python_cli_release_version_source())
    errors.extend(check_react_native_release_tags())
    errors.extend(check_firmware_release_metadata())

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("release process guard checks passed")
    return 0


def check_desktop_codemagic_release() -> list[str]:
    path = ROOT / "codemagic.yaml"
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "omi-desktop-swift-release:" not in text:
        errors.append("codemagic.yaml is missing the omi-desktop-swift-release workflow")

    planner = ROOT / ".github/scripts/plan-desktop-release.py"
    planner_text = planner.read_text(encoding="utf-8")
    if "AUTO_RELEASE_QUIET_SECONDS = 60" not in planner_text:
        errors.append("desktop auto-release planner must keep a short (60s) quiet window before auto-tagging")
    if "latest_change_age is None" not in planner_text:
        errors.append("desktop auto-release planner must fail closed when latest change age cannot be determined")
    if "RECENT_TAG_WITHOUT_CHECK_SECONDS = 10 * 60" not in planner_text:
        errors.append("desktop auto-release planner must keep the recent-tag lease for Codemagic checks")

    if "os.environ['BUILD_NAME']" in text or 'os.environ["BUILD_NAME"]' in text:
        errors.append("desktop Firestore bridge reads BUILD_NAME, but desktop release sets VERSION")

    if "edSignature: ${ED_SIGNATURE}" in text:
        empty_signature_block = re.search(
            r'if \[ -z "\$ED_SIGNATURE" \]; then(?:(?!\bfi\b).)*\bexit 1\b',
            text,
            flags=re.DOTALL,
        )
        if empty_signature_block is None:
            errors.append("desktop release can publish an empty Sparkle EdDSA signature")

    required_files = [
        "desktop/macos/scripts/prepare-agent-runtime.sh",
        "desktop/macos/scripts/prepare-desktop-bundle-native-deps.sh",
        "desktop/macos/scripts/publish-desktop-debug-symbols.sh",
        "desktop/macos/scripts/audit-desktop-bundle-deps.sh",
        "desktop/macos/scripts/create-desktop-dmgs.sh",
        "desktop/macos/scripts/create-omi-beta-variant.sh",
        "desktop/macos/scripts/notarize-desktop-artifacts.sh",
        "desktop/macos/scripts/smoke-signed-desktop-artifact.sh",
        "desktop/macos/Desktop/Omi-Release.entitlements",
        "desktop/macos/Desktop/Node.entitlements",
        "desktop/macos/dmg-assets/dmgbuild_settings.py",
        "scripts/scan-public-artifact-secrets.py",
        ".github/scripts/desktop-changelog.py",
    ]
    for required_file in required_files:
        if not (ROOT / required_file).exists():
            errors.append(f"desktop release references missing file: {required_file}")

    desktop_workflow_match = re.search(
        r"\n  omi-desktop-swift-release:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)",
        text,
        flags=re.DOTALL,
    )
    if desktop_workflow_match is None:
        errors.append("codemagic.yaml is missing the omi-desktop-swift-release workflow body")
        desktop_workflow_body = ""
    else:
        desktop_workflow_body = desktop_workflow_match.group("body")

    for required_fragment in (
        "publish-desktop-debug-symbols.sh generate",
        "publish-desktop-debug-symbols.sh upload",
        '"$DSYM_ARCHIVE"',
        "- build/*.dSYM",
        "source scripts/launcher-bootstrap.sh",
        "omi_normalize_packaged_resource_bundle",
        '"$APP_BUNDLE/Contents/Resources/$(basename "$RESOURCE_BUNDLE")"',
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop release is missing required release fragment: {required_fragment}")

    smoke_index = desktop_workflow_body.find("Smoke signed desktop artifact")
    beta_smoke_index = desktop_workflow_body.find("Smoke signed desktop beta artifact")
    prepare_beta_index = desktop_workflow_body.find("Prepare Omi Beta identity")
    notarize_apps_index = desktop_workflow_body.find("Notarize stable and Beta apps concurrently")
    create_dmgs_index = desktop_workflow_body.find("Create stable and Beta DMGs concurrently")
    notarize_dmgs_index = desktop_workflow_body.find("Notarize stable and Beta DMGs concurrently")
    sparkle_index = desktop_workflow_body.find("Create stable and Beta Sparkle archives")
    release_index = desktop_workflow_body.find("Create GitHub release")
    promotion_index = desktop_workflow_body.find("Promote signed candidate to Omi Beta")
    if not (
        -1
        < prepare_beta_index
        < notarize_apps_index
        < create_dmgs_index
        < notarize_dmgs_index
        < sparkle_index
        < smoke_index
    ):
        errors.append(
            "desktop release must prepare both identities, notarize apps, create DMGs, notarize DMGs, "
            "and sign Sparkle archives before smoke"
        )
    for required_fragment in (
        "scripts/notarize-desktop-artifacts.sh",
        "scripts/create-desktop-dmgs.sh",
        '--artifact stable "$APP_BUNDLE"',
        '--artifact beta "$BUILD_DIR/$BETA_APP_NAME.app"',
        '--artifact stable "$DMG_PATH"',
        '--artifact beta "$BETA_DMG_PATH"',
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"parallel desktop packaging is missing required fragment: {required_fragment}")
    if smoke_index == -1:
        errors.append("desktop release must run the signed artifact smoke before publishing the GitHub release")
    elif release_index == -1 or smoke_index > release_index:
        errors.append("desktop signed artifact smoke must run before Create GitHub release")
    if beta_smoke_index == -1:
        errors.append("desktop release must run the signed Omi Beta artifact smoke in a distinct provider step")
    elif release_index == -1 or not (smoke_index < beta_smoke_index < release_index):
        errors.append(
            "desktop signed Omi Beta artifact smoke must run after stable smoke and before Create GitHub release"
        )
    if promotion_index == -1 or release_index == -1 or promotion_index < release_index:
        errors.append("desktop release must promote the signed candidate after GitHub publication")
    reserve_index = desktop_workflow_body.find("/v2/desktop/beta/candidates/reserve")
    canonical_publish_index = desktop_workflow_body.find('gh release create "$CM_TAG"')
    if (
        reserve_index == -1
        or canonical_publish_index == -1
        or not (smoke_index < beta_smoke_index < reserve_index < canonical_publish_index)
    ):
        errors.append(
            "desktop release must reserve its exact candidate after signed smoke and before canonical publication"
        )
    for required_fragment in (
        'Authorization: Bearer ${BETA_PROMOTION_TOKEN}',
        '--data "{\\"tag\\":\\"${CM_TAG}\\"}"',
        'test -n "${BETA_PROMOTION_TOKEN:-}"',
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop candidate reservation is missing fail-closed fragment: {required_fragment}")
    for required_fragment in (
        "for attempt in 1 2 3",
        "/v2/desktop/beta/promote-candidate",
        "Retries are idempotent",
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop Beta promotion is missing reliable handoff fragment: {required_fragment}")
    promotion_body = desktop_workflow_body[promotion_index:] if promotion_index != -1 else ""
    if "gh workflow run desktop_qualify_beta.yml" in desktop_workflow_body:
        errors.append("Codemagic must not dispatch the retired Beta qualification gate")
    if "gh release edit \"$CM_TAG\"" in promotion_body:
        errors.append("Codemagic must not write release-body dispatch state outside the trusted workflow serialiser")
    if "candidate remains non-live" not in desktop_workflow_body:
        errors.append("desktop promotion handoff must state that a failed request cannot publish beta")
    if (
        "ERROR: Beta promotion was not confirmed after bounded retry" not in promotion_body
        or "exit 1" not in promotion_body
    ):
        errors.append("desktop promotion handoff must fail closed after bounded retries")
    if "gh release delete \"$CM_TAG\"" in desktop_workflow_body:
        errors.append("desktop candidate retries must not delete immutable qualification evidence")
    if "docker info" in desktop_workflow_body:
        errors.append("Codemagic desktop release must not run Docker-backed beta qualification")
    if "scripts/smoke-signed-desktop-artifact.sh" not in desktop_workflow_body:
        errors.append("desktop release smoke step must invoke scripts/smoke-signed-desktop-artifact.sh")
    stable_smoke_body = (
        desktop_workflow_body[smoke_index:beta_smoke_index] if smoke_index != -1 and beta_smoke_index != -1 else ""
    )
    beta_smoke_body = (
        desktop_workflow_body[beta_smoke_index:release_index] if beta_smoke_index != -1 and release_index != -1 else ""
    )
    for forbidden_fragment in ("--launch", "--auth-storage-canary", "--notification-callback-canary"):
        if forbidden_fragment in stable_smoke_body:
            errors.append(f"stable structural smoke must not run duplicate behavioral probe {forbidden_fragment}")
    for required_fragment in ("--launch", "--auth-storage-canary", "--notification-callback-canary"):
        if required_fragment not in beta_smoke_body:
            errors.append(f"signed Beta smoke is missing required behavioral probe {required_fragment}")

    smoke_script = ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"
    if smoke_script.exists():
        smoke_text = smoke_script.read_text(encoding="utf-8")
        for required_fragment in (
            "keychain-access-groups",
            "OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH",
            "OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND",
            "OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER",
            "result-json",
            "sha256",
            "TeamIdentifier",
            "Runtime Version",
            "https://api.omi.me/v2/desktop/appcast.xml",
            "audit-desktop-bundle-deps.sh",
            "notification-callback-canary",
            "UserNotifications settings callback completion canary passed",
            "OMI_NOTIFICATION_CALLBACK_SMOKE_RESULT_PATH",
        ):
            if required_fragment not in smoke_text:
                errors.append(f"signed artifact smoke is missing required guard fragment: {required_fragment}")

    automation_bridge = ROOT / "desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift"
    if automation_bridge.exists():
        automation_text = automation_bridge.read_text(encoding="utf-8")
        if (
            "AppBuild.allowsLocalAutomation" not in automation_text
            or "guard allowsLocalAutomation else" not in automation_text
        ):
            errors.append("desktop automation bridge must stay disabled for the production bundle")

    for required_fragment in (
        "--result-json \"$BUILD_DIR/desktop-smoke-result.json\"",
        "build/desktop-smoke-result.json",
        "desktop-smoke-result.json",
        "/v2/desktop/beta/promote-candidate",
        "BETA_PROMOTION_TOKEN",
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop release is missing signed smoke result artifact fragment: {required_fragment}")

    return errors


def check_desktop_candidate_trigger_authority() -> list[str]:
    """Keep the normal candidate lane on Codemagic's native immutable-tag trigger."""
    errors: list[str] = []
    codemagic = ROOT / "codemagic.yaml"
    candidate_workflow = ROOT / ".github/workflows/desktop_auto_release.yml"
    preview_workflow = ROOT / ".github/workflows/desktop_publish_preview.yml"
    if not codemagic.exists() or not candidate_workflow.exists() or not preview_workflow.exists():
        return ["desktop candidate trigger guard is missing its checked-in release surfaces"]

    codemagic_text = codemagic.read_text(encoding="utf-8")
    match = re.search(
        r"\n  omi-desktop-swift-release:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)",
        codemagic_text,
        flags=re.DOTALL,
    )
    required_trigger = (
        "    triggering:\n"
        "      events:\n"
        "        - tag\n"
        "      tag_patterns:\n"
        '        - pattern: "v*-macos"\n'
        "          include: true"
    )
    if match is None or required_trigger not in match.group("body"):
        errors.append("normal omi-desktop-swift-release candidate lane must natively trigger on v*-macos tags")

    direct_build_endpoint = "https://api.codemagic.io/builds"
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        if direct_build_endpoint not in workflow.read_text(encoding="utf-8"):
            continue
        if workflow != preview_workflow:
            errors.append(
                f"normal desktop candidate lane must not start Codemagic with a direct builds API POST: "
                f"{workflow.relative_to(ROOT)}"
            )

    preview_text = preview_workflow.read_text(encoding="utf-8")
    if direct_build_endpoint not in preview_text or 'workflowId: "omi-desktop-swift-preview"' not in preview_text:
        errors.append("the only checked-in direct Codemagic build API caller must remain the isolated preview lane")
    return errors


def check_desktop_preview_publishing() -> list[str]:
    """Keep the preview lane isolated from normal release authority and state."""
    errors: list[str] = []
    dispatcher = ROOT / ".github/workflows/desktop_publish_preview.yml"
    codemagic = ROOT / "codemagic.yaml"
    runtime_env = ROOT / "backend/deploy/runtime_env.yaml"
    app_build = ROOT / "desktop/macos/Desktop/Sources/AppBuild.swift"
    updater = ROOT / "desktop/macos/Desktop/Sources/UpdaterViewModel.swift"
    smoke = ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"
    preview_router = ROOT / "backend/routers/updates.py"
    preview_registry = ROOT / "backend/database/desktop_previews.py"

    if not dispatcher.exists():
        return ["desktop previews are missing the protected GitHub dispatcher"]
    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "source_ref:",
        "ref: main",
        "git ls-remote --exit-code origin",
        "^preview/",
        "environment: desktop-preview-publish",
        "CODEMAGIC_API_TOKEN",
        'workflowId: "omi-desktop-swift-preview"',
        'branch: "main"',
        "PREVIEW_SOURCE_SHA",
        "### Preview approval context",
        "https://github.com/${GITHUB_REPOSITORY}/commit/${PREVIEW_SOURCE_SHA}",
    ):
        if required not in dispatcher_text:
            errors.append(f"desktop preview dispatcher is missing required guard fragment: {required}")
    if "pull_request:" in dispatcher_text or "push:" in dispatcher_text:
        errors.append("desktop preview dispatcher must be manual-only")

    codemagic_text = codemagic.read_text(encoding="utf-8") if codemagic.exists() else ""
    preview_workflow_match = re.search(
        r"\n  omi-desktop-swift-preview:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)",
        codemagic_text,
        flags=re.DOTALL,
    )
    if preview_workflow_match is None:
        errors.append("codemagic.yaml is missing the preview publishing workflow")
    else:
        preview_workflow = preview_workflow_match.group("body")
        for required in (
            "desktop_preview_secrets",
            'PREVIEW_MODE: "true"',
            'DMGBUILD_VERSION: "1.6.7"',
            'DESKTOP_PREVIEW_REGISTRY_URL: "https://api.omi.me"',
            "git checkout --detach \"$PREVIEW_SOURCE_SHA\"",
            "--if-generation-match=0",
            "/previews/${PREVIEW_SLUG}/${PREVIEW_SOURCE_SHA}/Omi-Preview.dmg",
            "${DESKTOP_PREVIEW_REGISTRY_URL%/}/v2/desktop/previews/publish",
            "External previews do not create GitHub releases.",
            "External previews do not enter the shared Beta channel.",
        ):
            if required not in preview_workflow and required not in codemagic_text:
                errors.append(f"desktop preview workflow is missing required guard fragment: {required}")
        if "${OMI_PYTHON_API_URL%/}/v2/desktop/previews/publish" in codemagic_text:
            errors.append("desktop preview registry must not use the artifact runtime Python API URL")

    runtime_env_text = runtime_env.read_text(encoding="utf-8") if runtime_env.exists() else ""
    required_runtime_secret = (
        "            DESKTOP_PREVIEW_PUBLISH_KEY:\n"
        "              secret: DESKTOP_PREVIEW_PUBLISH_KEY\n"
        "              version: latest"
    )
    if required_runtime_secret not in runtime_env_text:
        errors.append("production backend must receive the preview publishing key from Secret Manager")

    preview_router_text = preview_router.read_text(encoding="utf-8") if preview_router.exists() else ""
    for required in (
        '@router.delete("/v2/desktop/previews/{slug}")',
        "DesktopPreviewDelistRequest",
        "delist_preview,",
        "expected_generation=request.expected_generation",
    ):
        if required not in preview_router_text:
            errors.append(f"desktop preview delisting is missing required router guard fragment: {required}")

    preview_registry_text = preview_registry.read_text(encoding="utf-8") if preview_registry.exists() else ""
    for required in (
        "def delist_preview(",
        "def _delist_preview_transaction(",
        "transaction.delete(pointer_ref)",
    ):
        if required not in preview_registry_text:
            errors.append(f"desktop preview delisting is missing required registry guard fragment: {required}")

    app_build_text = app_build.read_text(encoding="utf-8") if app_build.exists() else ""
    for required in (
        'externalPreviewBundleIdentifierPrefix = "com.omi.preview."',
        "allowsLocalAutomation",
        "allowsSparkleUpdates",
        "hasValidExternalPreviewConfiguration",
    ):
        if required not in app_build_text:
            errors.append(f"external preview build classification is missing: {required}")

    updater_text = updater.read_text(encoding="utf-8") if updater.exists() else ""
    if "startingUpdater: AppBuild.allowsSparkleUpdates" not in updater_text:
        errors.append("external preview builds must not start the shared Sparkle updater")

    smoke_text = smoke.read_text(encoding="utf-8") if smoke.exists() else ""
    for required in ("--preview", "IS_EXTERNAL_PREVIEW", "external preview must not carry a shared Sparkle feed"):
        if required not in smoke_text:
            errors.append(f"signed artifact smoke is missing external-preview check: {required}")

    return errors


def check_desktop_promotion_independent_of_qualification() -> list[str]:
    """Promotion and recovery must not reintroduce the deleted qualification lane."""
    errors: list[str] = []
    promotion = ROOT / ".github/workflows/desktop_promote_beta.yml"
    promotion_text = promotion.read_text(encoding="utf-8") if promotion.exists() else ""
    for required_fragment in (
        "workflow_call:",
        "release_tag:",
        "/v2/desktop/beta/promote-candidate",
        'Authorization: Bearer ${BETA_PROMOTION_TOKEN}',
        "environment: beta",
    ):
        if required_fragment not in promotion_text:
            errors.append(f"desktop beta promotion retry is missing signed-candidate guard: {required_fragment}")
    for forbidden_fragment in ("workflow_run:", "desktop_qualify_beta.yml", "qualification_run_id"):
        if forbidden_fragment in promotion_text:
            errors.append(f"desktop beta promotion retry still depends on qualification: {forbidden_fragment}")

    recovery = ROOT / ".github/workflows/desktop_recover_beta.yml"
    recovery_text = recovery.read_text(encoding="utf-8") if recovery.exists() else ""
    for required_fragment in (
        "uses: ./.github/workflows/desktop_promote_beta.yml",
        "release_tag:",
        "signed-smoke evidence",
    ):
        if required_fragment not in recovery_text:
            errors.append(f"desktop beta recovery workflow is missing signed-evidence guard: {required_fragment}")
    if "qualification_run_id" in recovery_text:
        errors.append("desktop beta recovery workflow still requires retired qualification identity")
    return errors


def check_desktop_update_docs() -> list[str]:
    """Keep operator docs aligned with Stable/Beta's signed artifact identities."""
    path = ROOT / "docs/doc/developer/desktop-updates.mdx"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    errors: list[str] = []
    required = (
        "Omi.app",
        "com.omi.computer-macos",
        "Omi.zip",
        "`omi.dmg`",
        "Omi Beta.app",
        "com.omi.computer-macos.beta",
        "Omi.Beta.zip",
        "omi-beta.dmg",
        "production Firebase Auth/Firestore",
        "Beta OAuth remains on the production identity authority",
    )
    forbidden = (
        "Beta is a server-side distribution channel, not a second app",
        "Every\nqualified macOS release has one identity",
    )
    for fragment in required:
        if fragment not in text:
            errors.append(f"desktop update docs are missing Stable/Beta artifact contract: {fragment}")
    for fragment in forbidden:
        if fragment in text:
            errors.append(f"desktop update docs retain forbidden single-identity claim: {fragment}")
    return errors


def check_no_unprovisioned_beta_backend_hosts() -> list[str]:
    """Production-family clients must share the established production backend.

    This keeps the #10090 beta-host routing regression from returning while
    deliberately excluding docs and Git history, where the retired names are
    useful migration evidence rather than shipped routing.
    """
    hosts = ("api-beta.omi.me", "pusher-beta.omi.me", "agent-beta.omi.me")
    paths = [ROOT / "app", ROOT / "desktop/macos", ROOT / "codemagic.yaml", ROOT / ".github/workflows"]
    non_shipped_parts = {".build", ".dart_tool", "Pods", "test", "tests", "Tests", "test_driver"}
    errors: list[str] = []
    for path in paths:
        files = (
            [path]
            if path.is_file()
            else [
                item
                for item in path.rglob("*")
                if item.is_file() and not non_shipped_parts.intersection(item.relative_to(path).parts)
            ]
        )
        for file in files:
            try:
                text = file.read_text(encoding="utf-8")
            except (FileNotFoundError, UnicodeDecodeError):
                continue
            for host in hosts:
                if host in text:
                    errors.append(
                        f"shipped release source references unprovisioned beta backend host {host}: {file.relative_to(ROOT)}"
                    )
    return errors


def check_mobile_codemagic_release_triggers() -> list[str]:
    errors: list[str] = []
    codemagic = ROOT / "codemagic.yaml"
    codemagic_text = codemagic.read_text(encoding="utf-8")

    for workflow_id in ("ios-internal-auto", "android-internal-auto"):
        pattern = rf"\n  {re.escape(workflow_id)}:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)"
        match = re.search(pattern, codemagic_text, flags=re.DOTALL)
        if match is None:
            errors.append(f"codemagic.yaml is missing {workflow_id}")
            continue
        body = match.group("body")
        if "    when:\n      changeset:\n        includes:\n          - 'app/**'" not in body:
            errors.append(f"{workflow_id} must retain its app/** changeset guard")

    dispatcher = ROOT / ".github/workflows/mobile_internal_build.yml"
    if not dispatcher.exists():
        errors.append("mobile internal build dispatcher is missing")
    else:
        dispatcher_text = dispatcher.read_text(encoding="utf-8")
        dispatcher_script = ROOT / ".github/scripts/dispatch_mobile_internal_builds.py"
        try:
            workflow = yaml.load(dispatcher_text, Loader=yaml.BaseLoader)
        except yaml.YAMLError as exc:
            errors.append(f"mobile internal build dispatcher is not valid YAML: {exc}")
            workflow = None
        if not isinstance(workflow, dict):
            errors.append("mobile internal build dispatcher must be a YAML mapping")
        else:
            triggers = workflow.get("on")
            if not isinstance(triggers, dict):
                errors.append(
                    "mobile internal build dispatcher must declare push, schedule, and workflow_dispatch triggers"
                )
            else:
                push = triggers.get("push")
                if not isinstance(push, dict) or push.get("branches") != ["main"] or push.get("paths") != ["app/**"]:
                    errors.append("mobile internal build dispatcher must trigger on main app/** pushes")
                schedule = triggers.get("schedule")
                if not isinstance(schedule, list) or schedule != [{"cron": "0 */3 * * *"}]:
                    errors.append("mobile internal build dispatcher must retain its three-hour schedule")
                if "workflow_dispatch" not in triggers:
                    errors.append("mobile internal build dispatcher must retain workflow_dispatch")
            concurrency = workflow.get("concurrency")
            if not isinstance(concurrency, dict) or concurrency.get("group") != "mobile-internal-build":
                errors.append("mobile internal build dispatcher must use the mobile-internal-build concurrency group")
            elif concurrency.get("cancel-in-progress") != "false":
                errors.append("mobile internal build dispatcher must not cancel an in-progress sequential dispatch")
            jobs = workflow.get("jobs")
            dispatch_job = jobs.get("dispatch") if isinstance(jobs, dict) else None
            steps = dispatch_job.get("steps") if isinstance(dispatch_job, dict) else None
            runs = [step.get("run", "") for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []
            if not any("python3 .github/scripts/dispatch_mobile_internal_builds.py" in run for run in runs):
                errors.append("mobile internal build dispatcher must invoke dispatch_mobile_internal_builds.py")

        if not dispatcher_script.exists():
            errors.append("mobile internal build dispatcher script is missing")
        else:
            try:
                script_tree = ast.parse(dispatcher_script.read_text(encoding="utf-8"), filename=str(dispatcher_script))
            except (OSError, SyntaxError) as exc:
                errors.append(f"mobile internal build dispatcher script is not valid Python: {exc}")
            else:
                workflow_values = None
                for node in script_tree.body:
                    if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "MOBILE_WORKFLOWS" for target in node.targets
                    ):
                        try:
                            workflow_values = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            workflow_values = None
                        break
                if workflow_values != ("ios-internal-auto", "android-internal-auto"):
                    errors.append(
                        "mobile internal build dispatcher script must declare both Codemagic mobile workflows"
                    )

    if (ROOT / ".github/workflows/mobile_internal_auto.yml").exists():
        errors.append("mobile internal releases must not be dispatched through GitHub Actions")

    return errors


def check_docs_workflow_scripts() -> list[str]:
    workflow = ROOT / ".github/workflows/deploy_docs.yml"
    package_json = ROOT / "docs/package.json"
    if not workflow.exists() or not package_json.exists():
        return []

    text = workflow.read_text(encoding="utf-8")
    scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
    errors = []
    for script in sorted(set(re.findall(r"npm run ([A-Za-z0-9:_-]+)", text))):
        if script not in scripts:
            errors.append(f"deploy_docs.yml runs npm script {script!r}, but docs/package.json does not define it")
    return errors


def check_python_cli_release_version_source() -> list[str]:
    release_script = ROOT / "sdks/python-cli/release.sh"
    if not release_script.exists():
        return []

    text = release_script.read_text(encoding="utf-8")
    if "['project']['version']" in text or '["project"]["version"]' in text:
        return ["sdks/python-cli/release.sh reads project.version, but pyproject.toml uses dynamic versioning"]
    if "import omi_cli" not in text or "__version__" not in text:
        return ["sdks/python-cli/release.sh must resolve the version from omi_cli.__version__"]
    return []


def check_react_native_release_tags() -> list[str]:
    package_json = ROOT / "sdks/react-native/package.json"
    podspec = ROOT / "sdks/react-native/omi-react-native.podspec"
    if not package_json.exists() or not podspec.exists():
        return []

    package = json.loads(package_json.read_text(encoding="utf-8"))
    release_tag = package.get("release-it", {}).get("git", {}).get("tagName")
    podspec_text = podspec.read_text(encoding="utf-8")
    if release_tag == "v${version}" and ':tag => "v#{s.version}"' not in podspec_text:
        return ["React Native podspec tag must match release-it tagName v${version}"]
    return []


def check_firmware_release_metadata() -> list[str]:
    script = ROOT / "omi/firmware/scripts/ci/make-release-body.sh"
    workflow = ROOT / ".github/workflows/firmware_release.yml"
    if not script.exists():
        return []

    try:
        bash = bash_executable()
    except FileNotFoundError as exc:
        return [f"firmware release body smoke failed: {exc}"]

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "body.md"
        env = {
            "TITLE": "Omi CV1 Firmware v9.8.7",
            "VER": "9.8.7",
            "CHANGELOG": "Guard smoke test",
            "MIN_FW": "3.0.6",
            "MIN_APP": "1.0.74",
            "MIN_APP_CODE": "438",
            "OTA_STEPS": "battery,internet",
            "IS_LEGACY_SECURE_DFU": "False",
            "OUT": bash_path(output, bash),
        }
        completed = subprocess.run(
            [bash, str(script)],
            cwd=ROOT,
            env={**os.environ, **env},
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            return [f"firmware release body smoke failed: {detail or f'exit {completed.returncode}'}"]
        body = output.read_text(encoding="utf-8")

    kv = extract_key_value_pairs(body)
    errors = []
    if kv.get("release_firmware_version") != "9.8.7":
        errors.append("firmware release body must include release_firmware_version")
    if kv.get("minimum_firmware_required") != "3.0.6":
        errors.append("firmware release body must include minimum_firmware_required")
    if kv.get("minimum_app_version") != "1.0.74":
        errors.append("firmware release body must include minimum_app_version")
    if kv.get("minimum_app_version_code") != "438":
        errors.append("firmware release body must include minimum_app_version_code")
    if kv.get("is_legacy_secure_dfu") != "False":
        errors.append("CV1 firmware release body must emit is_legacy_secure_dfu:False")
    if "ota_update_steps" not in kv:
        errors.append("firmware release body must include ota_update_steps when provided")
    if workflow.exists():
        workflow_text = workflow.read_text(encoding="utf-8")
        ota_asset = r'Omi_CV1_OTA_v$VER.zip'
        if ota_asset not in workflow_text:
            errors.append("firmware release workflow must stage and publish an OTA .zip asset")
    return errors


def extract_key_value_pairs(markdown_content: str) -> dict[str, str]:
    match = re.search(r"<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->", markdown_content, re.DOTALL)
    if not match:
        return {}

    result: dict[str, str] = {}
    for line in match.group(1).strip().split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
