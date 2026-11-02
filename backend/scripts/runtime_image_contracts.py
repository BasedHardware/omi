#!/usr/bin/env python3
"""Verify that deployable Python images contain their reachable first-party imports.

The local checkout has every backend package on its import path; a Docker image does
not.  This module treats the final runtime stage's COPY instructions as the source of
truth, stages that exact source surface in a temporary directory, and walks imports
from each declared entrypoint.  It catches a first-party package omitted from a
whitelist Dockerfile without building an image.

``smoke`` is intentionally separate: it checks every reachable third-party module
is installed in an already-built image with no network, then imports isolated
entrypoints where that is side-effect safe. GPU images use the dependency-presence
probe but defer a full import until model initialization is lazy.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPOSITORY_ROOT / "backend" / "runtime_images.json"
IGNORED_SOURCE_DIRECTORIES = {".git", ".pytest_cache", ".venv", ".openapi-venv", "__pycache__"}
# First-party modules that raise at import time unless an environment variable is set.
# An import smoke reaching one of these without the variable fails the deploy, so the
# registry must declare a non-production placeholder in ``smoke_environment``.
IMPORT_TIME_REQUIRED_ENVIRONMENT = {"utils.encryption": "ENCRYPTION_SECRET"}


@dataclass(frozen=True)
class ImageContract:
    name: str
    dockerfile: Path
    deployment_workflows: tuple[Path, ...]
    build_context: Path
    source_root: Path
    entrypoint_source_root: Path
    workdir: PurePosixPath
    entrypoints: tuple[str, ...]
    image_import_smoke: bool
    smoke_python: str
    smoke_environment: tuple[tuple[str, str], ...]
    smoke_entrypoints: tuple[str, ...]
    smoke_prelude: str
    dependency_probe_smoke: bool
    dependency_probe_exclusions: frozenset[str]
    pull_request_smoke: bool
    # Build stage for multi-target Dockerfiles; None means the last stage.
    target: str | None = None
    # Built and smoked as a check only; no deployment workflow ships it yet.
    build_only: bool = False


@dataclass(frozen=True)
class DockerStage:
    name: str | None
    parent: str
    instructions: tuple[str, ...]


@dataclass(frozen=True)
class CopyInstruction:
    sources: tuple[str, ...]
    destination: str


class ContractError(ValueError):
    """Raised when the registry or a Dockerfile cannot define a deterministic contract."""


def _repository_relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix() if path.is_relative_to(REPOSITORY_ROOT) else path.as_posix()


def load_contracts(
    registry_path: Path = REGISTRY_PATH,
    *,
    dockerfile_filter: Path | None = None,
) -> list[ImageContract]:
    """Load and validate runtime-image contracts from the registry.

    When ``dockerfile_filter`` is set, entries whose ``dockerfile`` does not
    resolve to that path are skipped before filesystem validation.  This lets
    the ``smoke`` command run against a deploy-staged source tree that contains
    only the requested image's source surface (e.g. ``backend`` and ``.github``)
    without failing on unrelated absent source roots such as ``plugins``.
    """
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read runtime-image registry {registry_path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ContractError("runtime-image registry must be an object with schema_version 1")
    entries = payload.get("images")
    if not isinstance(entries, list) or not entries:
        raise ContractError("runtime-image registry must declare at least one image")

    contracts: list[ImageContract] = []
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractError("every runtime-image entry must be an object")
        required_strings = ("name", "dockerfile", "build_context", "source_root", "workdir")
        if any(not isinstance(entry.get(key), str) or not entry[key] for key in required_strings):
            raise ContractError(f"runtime-image entry has invalid required fields: {entry!r}")
        if dockerfile_filter is not None:
            entry_dockerfile = REPOSITORY_ROOT / entry["dockerfile"]
            if entry_dockerfile.resolve() != dockerfile_filter.resolve():
                continue
        entrypoints_raw = entry.get("entrypoints")
        if (
            not isinstance(entrypoints_raw, list)
            or not entrypoints_raw
            or any(not isinstance(module, str) or not module for module in entrypoints_raw)
        ):
            raise ContractError(f"{entry['name']}: entrypoints must be a non-empty list of module names")
        if not isinstance(entry.get("image_import_smoke"), bool):
            raise ContractError(f"{entry['name']}: image_import_smoke must be boolean")
        smoke_python = entry.get("smoke_python", "python")
        if not isinstance(smoke_python, str) or not smoke_python:
            raise ContractError(f"{entry['name']}: smoke_python must be a non-empty string")
        smoke_entrypoints_raw = entry.get("smoke_entrypoints", entrypoints_raw)
        if (
            not isinstance(smoke_entrypoints_raw, list)
            or not smoke_entrypoints_raw
            or any(not isinstance(module, str) or not module for module in smoke_entrypoints_raw)
        ):
            raise ContractError(f"{entry['name']}: smoke_entrypoints must be a non-empty list of module names")
        smoke_prelude = entry.get("smoke_prelude", "")
        if not isinstance(smoke_prelude, str):
            raise ContractError(f"{entry['name']}: smoke_prelude must be a string")
        if not isinstance(entry.get("dependency_probe_smoke"), bool):
            raise ContractError(f"{entry['name']}: dependency_probe_smoke must be boolean")
        if not isinstance(entry.get("pull_request_smoke"), bool):
            raise ContractError(f"{entry['name']}: pull_request_smoke must be boolean")
        dependency_probe_exclusions_raw = entry.get("dependency_probe_exclusions", {})
        if not isinstance(dependency_probe_exclusions_raw, dict) or any(
            not isinstance(module, str) or not module or not isinstance(reason, str) or not reason
            for module, reason in dependency_probe_exclusions_raw.items()
        ):
            raise ContractError(f"{entry['name']}: dependency_probe_exclusions must map module names to reasons")
        smoke_environment_raw = entry.get("smoke_environment", {})
        if not isinstance(smoke_environment_raw, dict) or any(
            not isinstance(key, str) or not key or not isinstance(value, str)
            for key, value in smoke_environment_raw.items()
        ):
            raise ContractError(f"{entry['name']}: smoke_environment must be a string-to-string object")
        if entry["name"] in names:
            raise ContractError(f"duplicate runtime-image name: {entry['name']}")
        names.add(entry["name"])
        target = entry.get("target")
        if target is not None and (not isinstance(target, str) or not target):
            raise ContractError(f"{entry['name']}: target must be a non-empty build stage name")
        build_only = entry.get("build_only", False)
        if not isinstance(build_only, bool):
            raise ContractError(f"{entry['name']}: build_only must be boolean")
        deployment_workflows_raw = entry.get("deployment_workflows")
        if build_only:
            if deployment_workflows_raw != []:
                raise ContractError(
                    f"{entry['name']}: a build_only image declares deployment_workflows as [] until a deploy ships it"
                )
            if not entry["pull_request_smoke"] or not entry["dependency_probe_smoke"]:
                raise ContractError(
                    f"{entry['name']}: a build_only image exists to be built and probed; "
                    "pull_request_smoke and dependency_probe_smoke must be true"
                )
        elif (
            not isinstance(deployment_workflows_raw, list)
            or not deployment_workflows_raw
            or any(not isinstance(workflow, str) or not workflow for workflow in deployment_workflows_raw)
        ):
            raise ContractError(f"{entry['name']}: deployment_workflows must be a non-empty list of paths")
        dockerfile = REPOSITORY_ROOT / entry["dockerfile"]
        deployment_workflows = tuple(REPOSITORY_ROOT / workflow for workflow in deployment_workflows_raw)
        build_context = REPOSITORY_ROOT / entry["build_context"]
        source_root = REPOSITORY_ROOT / entry["source_root"]
        entrypoint_source_root = REPOSITORY_ROOT / entry.get("entrypoint_source_root", entry["source_root"])
        if not dockerfile.is_file():
            raise ContractError(f"{entry['name']}: Dockerfile does not exist: {entry['dockerfile']}")
        if any(not workflow.is_file() for workflow in deployment_workflows):
            raise ContractError(f"{entry['name']}: a declared deployment workflow does not exist")
        if not build_context.is_dir():
            raise ContractError(f"{entry['name']}: build context does not exist: {entry['build_context']}")
        if not source_root.is_dir():
            raise ContractError(f"{entry['name']}: source root does not exist: {entry['source_root']}")
        if not entrypoint_source_root.is_dir():
            raise ContractError(f"{entry['name']}: entrypoint source root does not exist")
        if target is not None and target not in {stage.name for stage in docker_named_stages(dockerfile)}:
            raise ContractError(f"{entry['name']}: target stage {target!r} is not defined in {entry['dockerfile']}")
        contracts.append(
            ImageContract(
                name=entry["name"],
                dockerfile=dockerfile,
                deployment_workflows=deployment_workflows,
                build_context=build_context,
                source_root=source_root,
                entrypoint_source_root=entrypoint_source_root,
                workdir=PurePosixPath(entry["workdir"]),
                entrypoints=tuple(entrypoints_raw),
                image_import_smoke=entry["image_import_smoke"],
                smoke_python=smoke_python,
                smoke_environment=tuple(sorted(smoke_environment_raw.items())),
                smoke_entrypoints=tuple(smoke_entrypoints_raw),
                smoke_prelude=smoke_prelude,
                dependency_probe_smoke=entry["dependency_probe_smoke"],
                dependency_probe_exclusions=frozenset(dependency_probe_exclusions_raw),
                pull_request_smoke=entry["pull_request_smoke"],
                target=target,
                build_only=build_only,
            )
        )
    return contracts


def _logical_docker_lines(path: Path) -> list[str]:
    logical_lines: list[str] = []
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending}{stripped}" if pending else stripped
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip() + " "
            continue
        logical_lines.append(pending)
        pending = ""
    if pending:
        logical_lines.append(pending)
    return logical_lines


def docker_stages(dockerfile: Path) -> list[list[str]]:
    stages: list[list[str]] = []
    current_stage: list[str] | None = None
    for line in _logical_docker_lines(dockerfile):
        if line.upper().startswith("FROM "):
            current_stage = []
            stages.append(current_stage)
            continue
        if current_stage is not None:
            current_stage.append(line)
    if not stages:
        raise ContractError(f"{_repository_relative(dockerfile)} has no Docker stage")
    return stages


def docker_named_stages(dockerfile: Path) -> list[DockerStage]:
    """Return each stage with its ``AS`` name and the image or stage it builds ``FROM``."""
    headers: list[tuple[str | None, str]] = []
    for line in _logical_docker_lines(dockerfile):
        if line.upper().startswith("FROM "):
            tokens = [token for token in line.split()[1:] if not token.startswith("--")]
            name = tokens[2] if len(tokens) == 3 and tokens[1].upper() == "AS" else None
            headers.append((name, tokens[0] if tokens else ""))
    return [
        DockerStage(name=name, parent=parent, instructions=tuple(instructions))
        for (name, parent), instructions in zip(headers, docker_stages(dockerfile), strict=True)
    ]


def docker_target_instructions(dockerfile: Path, target: str | None = None) -> list[str]:
    """Return the filesystem-relevant instructions of ``target`` (default: last stage).

    A stage built ``FROM`` an earlier stage of the same Dockerfile inherits that
    stage's layers, so the result concatenates the chain from the root stage to
    ``target`` in build order. ``COPY --from`` is a copy, not inheritance.
    """
    stages = docker_named_stages(dockerfile)
    by_name = {stage.name: stage for stage in stages if stage.name}
    if target is None:
        stage = stages[-1]
    elif target in by_name:
        stage = by_name[target]
    else:
        raise ContractError(f"{_repository_relative(dockerfile)} has no build stage {target!r}")
    chain = [stage]
    while chain[-1].parent in by_name:
        parent = by_name[chain[-1].parent]
        if parent in chain:
            raise ContractError(f"{_repository_relative(dockerfile)} has a cyclic stage chain at {parent.name!r}")
        chain.append(parent)
    return [line for ancestor in reversed(chain) for line in ancestor.instructions]


def final_stage_copy_instructions(dockerfile: Path, target: str | None = None) -> list[CopyInstruction]:
    copies: list[CopyInstruction] = []
    for line in docker_target_instructions(dockerfile, target):
        if not line.upper().startswith("COPY "):
            continue
        tokens = shlex.split(line[5:])
        if any(token.startswith("--from=") for token in tokens):
            continue
        tokens = [token for token in tokens if not token.startswith("--")]
        if len(tokens) < 2:
            raise ContractError(f"cannot parse COPY instruction in {_repository_relative(dockerfile)}: {line}")
        copies.append(CopyInstruction(sources=tuple(tokens[:-1]), destination=tokens[-1]))
    return copies


def _copy_destination(line: str) -> str | None:
    if not line.upper().startswith("COPY "):
        return None
    tokens = [token for token in shlex.split(line[5:]) if not token.startswith("--")]
    return tokens[-1] if len(tokens) >= 2 else None


def final_stage_layer_errors(contract: ImageContract) -> list[str]:
    """Reject bytes hidden by later layers and installs shadowed by a late venv copy."""
    instructions = docker_target_instructions(contract.dockerfile, contract.target)
    errors: list[str] = []

    copied_destinations: dict[str, int] = {}
    path_venvs: dict[str, int] = {}
    for index, line in enumerate(instructions):
        if line.upper().startswith("COPY "):
            destination = _copy_destination(line)
            if destination:
                copied_destinations[destination.rstrip("/")] = index
            continue
        if line.upper().startswith("ENV PATH="):
            path_value = line.split("=", 1)[1].strip('"\'')
            first_entry = path_value.split(":", 1)[0]
            if first_entry.endswith("/bin"):
                path_venvs[first_entry[: -len("/bin")].rstrip("/")] = index

    for destination, copy_index in copied_destinations.items():
        for line in instructions[copy_index + 1 :]:
            if line.upper().startswith("RUN ") and any(
                marker in line for marker in (f"rm -rf {destination}", f"rm -r {destination}")
            ):
                errors.append(
                    f"{contract.name}: final-stage COPY to {destination!r} is removed in a later RUN layer; "
                    "the copied bytes remain in the image manifest"
                )
                break

    for venv, path_index in path_venvs.items():
        copy_index = copied_destinations.get(venv)
        if copy_index is None or copy_index <= path_index:
            continue
        for line in instructions[path_index + 1 : copy_index]:
            if line.upper().startswith("RUN ") and "pip install" in line:
                errors.append(
                    f"{contract.name}: {venv!r} leads PATH but pip runs before that environment is copied into "
                    "the final stage; the install is shadowed at runtime"
                )
                break

    return errors


def _ignore_source_directory(_: str, names: list[str]) -> set[str]:
    skipped = {name for name in names if name in IGNORED_SOURCE_DIRECTORIES}
    names[:] = [name for name in names if name not in skipped]
    return skipped


def _runtime_destination(destination: str, workdir: PurePosixPath) -> Path:
    destination_path = PurePosixPath(destination)
    if destination_path.is_absolute():
        try:
            destination_path = destination_path.relative_to(workdir)
        except ValueError as exc:
            raise ContractError(f"COPY destination {destination!r} is outside WORKDIR {workdir}") from exc
    return Path(destination_path.as_posix())


def _copy_source(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=_ignore_source_directory)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def stage_runtime_sources(contract: ImageContract, runtime_root: Path) -> None:
    for instruction in final_stage_copy_instructions(contract.dockerfile, contract.target):
        destination = _runtime_destination(instruction.destination, contract.workdir)
        for source_pattern in instruction.sources:
            if "$" in source_pattern:
                continue
            source_paths = sorted(contract.build_context.glob(source_pattern))
            if not source_paths:
                raise ContractError(
                    f"{contract.name}: COPY source {source_pattern!r} does not exist in {_repository_relative(contract.build_context)}"
                )
            for source in source_paths:
                if source.is_dir():
                    target = runtime_root / destination
                    if len(instruction.sources) > 1 or len(source_paths) > 1:
                        target /= source.name
                elif instruction.destination.endswith("/") or instruction.destination in {".", "./"}:
                    target = runtime_root / destination / source.name
                else:
                    target = runtime_root / destination
                _copy_source(source, target)


def _module_path(root: Path, module: str) -> Path | None:
    module_path = Path(*module.split("."))
    candidates = (root / f"{module_path}.py", root / module_path / "__init__.py")
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _first_party_source_roots(contract: ImageContract) -> tuple[Path, ...]:
    """Return all checkout roots that contribute top-level modules to an image."""
    return tuple(dict.fromkeys((contract.entrypoint_source_root, contract.source_root)))


def _find_module_source(source_roots: Iterable[Path], module: str) -> tuple[Path, Path] | None:
    for root in source_roots:
        path = _module_path(root, module)
        if path is not None:
            return path, root
    return None


def _module_or_namespace_exists(source_roots: Iterable[Path], module: str) -> bool:
    for root in source_roots:
        module_path = root.joinpath(*module.split("."))
        if _module_path(root, module) is not None or (module_path.is_dir() and any(module_path.rglob("*.py"))):
            return True
    return False


def _imported_modules(
    tree: ast.AST,
    current_module: str,
    source_roots: Iterable[Path],
    current_is_package: bool,
    *,
    include_from_import_candidates: bool = False,
) -> set[str]:
    imported: set[str] = set()
    current_parts = current_module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = current_parts if current_is_package else current_parts[:-1]
                parent_levels = node.level - 1
                if parent_levels > len(package_parts):
                    continue
                prefix = package_parts[: len(package_parts) - parent_levels]
                base = ".".join(part for part in (*prefix, *(node.module or "").split(".")) if part)
            else:
                base = node.module or ""
            if base:
                imported.add(base)
                for alias in node.names:
                    candidate = f"{base}.{alias.name}"
                    if alias.name != "*" and (
                        include_from_import_candidates or _module_or_namespace_exists(source_roots, candidate)
                    ):
                        imported.add(candidate)
    return imported


def source_closure_errors(contract: ImageContract) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix=f"omi-runtime-image-{contract.name}-") as temp_dir:
        runtime_root = Path(temp_dir)
        stage_runtime_sources(contract, runtime_root)
        visited: set[str] = set()
        source_roots = _first_party_source_roots(contract)

        def visit(module: str, imported_by: str | None = None) -> None:
            if module in visited:
                return
            visited.add(module)
            source = _find_module_source(source_roots, module)
            if source is None:
                return
            source_path, _ = source
            runtime_path = _module_path(runtime_root, module)
            if runtime_path is None:
                location = f" imported by {imported_by}" if imported_by else ""
                errors.append(
                    f"{contract.name}: first-party module {module!r}{location} is absent from the final runtime COPY surface"
                )
                return
            try:
                tree = ast.parse(runtime_path.read_text(encoding="utf-8"), filename=str(runtime_path))
            except SyntaxError as exc:
                errors.append(f"{contract.name}: staged module {module!r} has invalid syntax: {exc}")
                return
            for dependency in sorted(
                _imported_modules(tree, module, source_roots, current_is_package=source_path.name == "__init__.py")
            ):
                top_level = dependency.split(".", 1)[0]
                if _module_or_namespace_exists(source_roots, top_level):
                    if not _module_or_namespace_exists((runtime_root,), dependency):
                        errors.append(
                            f"{contract.name}: first-party module {dependency!r} imported by {module} "
                            "is absent from the final runtime COPY surface"
                        )
                        continue
                    visit(dependency, module)

        for entrypoint in contract.entrypoints:
            visit(entrypoint)
    return errors


def first_party_import_closure(contract: ImageContract, entrypoints: Iterable[str]) -> set[str]:
    """Return the first-party modules reachable from ``entrypoints`` in the checkout."""
    source_roots = _first_party_source_roots(contract)
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visited:
            return
        visited.add(module)
        source = _find_module_source(source_roots, module)
        if source is None:
            return
        source_path, _ = source
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for imported in _imported_modules(
            tree, module, source_roots, current_is_package=source_path.name == "__init__.py"
        ):
            if _module_or_namespace_exists(source_roots, imported.split(".", 1)[0]):
                visit(imported)

    for entrypoint in entrypoints:
        visit(entrypoint)
    return visited


def import_smoke_environment_errors(contracts: Iterable[ImageContract]) -> list[str]:
    """Fail registrations whose import smoke would hit an import-time environment guard."""
    errors: list[str] = []
    for contract in contracts:
        if not contract.image_import_smoke:
            continue
        declared = dict(contract.smoke_environment)
        reachable = first_party_import_closure(contract, contract.smoke_entrypoints)
        for module, variable in sorted(IMPORT_TIME_REQUIRED_ENVIRONMENT.items()):
            if module in reachable and variable not in declared:
                errors.append(
                    f"{contract.name}: import smoke reaches {module!r}, which raises at import time "
                    f"unless {variable} is set; declare a non-production {variable} in smoke_environment"
                )
    return errors


def check_source_closures(contracts: Iterable[ImageContract]) -> list[str]:
    errors: list[str] = []
    for contract in contracts:
        errors.extend(final_stage_layer_errors(contract))
        errors.extend(source_closure_errors(contract))
    return errors


def _workflow_contract_text(workflow: Path) -> str:
    workflow_text = workflow.read_text(encoding="utf-8")
    scripts_dir = REPOSITORY_ROOT / ".github" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from workflow_composite_contract import backend_deploy_contract_text

    return backend_deploy_contract_text(
        workflow_text,
        REPOSITORY_ROOT,
        Path(".github/actions/deploy-backend-stack/action.yml"),
    )


def workflow_contract_errors(contracts: Iterable[ImageContract]) -> list[str]:
    errors: list[str] = []
    for contract in contracts:
        dockerfile = _repository_relative(contract.dockerfile)
        for workflow in contract.deployment_workflows:
            # Comments do not run: a marker left above a deleted step must not pass.
            workflow_text = "\n".join(
                line for line in _workflow_contract_text(workflow).splitlines() if not line.lstrip().startswith("#")
            )
            workflow_name = _repository_relative(workflow)
            if not any(
                marker in workflow_text
                # role_images.py verify runs this smoke per role target (backend/scripts/role_images.py).
                for marker in (
                    "runtime_image_contracts.py smoke",
                    'runtime_image_contracts.py" smoke',
                    "role_images.py verify",
                )
            ):
                errors.append(f"{contract.name}: {workflow_name} does not smoke its registered runtime image")
            if dockerfile not in workflow_text:
                errors.append(
                    f"{contract.name}: {workflow_name} does not reference registered Dockerfile {dockerfile} for its smoke"
                )
    return errors


def third_party_dependency_modules(contract: ImageContract) -> tuple[str, ...]:
    """Find reachable third-party import targets without executing application code.

    ``from google.cloud import tasks_v2`` records both ``google.cloud`` and
    ``google.cloud.tasks_v2``.  The latter is essential: checking only the
    namespace package would miss a missing optional distribution such as
    ``google-cloud-tasks``.  The smoke probe resolves imported attributes
    safely when a target is a symbol rather than a submodule.
    """
    source_roots = _first_party_source_roots(contract)
    visited: set[str] = set()
    dependencies: set[str] = set()

    def visit(module: str) -> None:
        if module in visited:
            return
        visited.add(module)
        source = _find_module_source(source_roots, module)
        if source is None:
            return
        source_path, _ = source
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for imported in _imported_modules(
            tree,
            module,
            source_roots,
            current_is_package=source_path.name == "__init__.py",
            include_from_import_candidates=True,
        ):
            top_level = imported.split(".", 1)[0]
            if _module_or_namespace_exists(source_roots, top_level):
                visit(imported)
            elif top_level not in sys.stdlib_module_names:
                dependencies.add(imported)

    for entrypoint in contract.entrypoints:
        visit(entrypoint)
    exclusions = tuple(contract.dependency_probe_exclusions)
    return tuple(
        sorted(
            dependency
            for dependency in dependencies
            if not any(dependency == excluded or dependency.startswith(f"{excluded}.") for excluded in exclusions)
        )
    )


def _dependency_probe_code(modules: tuple[str, ...]) -> str:
    """Return an offline probe for module paths and ``from`` import attributes.

    A failed import used to collapse to a bare missing-module name. The message
    now includes the exception type and first line so a version clash is visible
    in the image build log.
    """
    return (
        "import importlib, importlib.util\n"
        f"modules = {list(modules)!r}\n"
        "import_errors = []\n"
        "def record_import_error(target, exc):\n"
        "    message = str(exc).splitlines()[0][:300] if str(exc) else ''\n"
        "    item = f'{target}: {type(exc).__name__}: {message}'.rstrip()\n"
        "    if item not in import_errors:\n"
        "        import_errors.append(item)\n"
        "def is_importable(target):\n"
        "    try:\n"
        "        if importlib.util.find_spec(target) is not None:\n"
        "            return True\n"
        "    except (ImportError, AttributeError, ModuleNotFoundError) as exc:\n"
        "        record_import_error(target, exc)\n"
        "    parent, separator, attribute = target.rpartition('.')\n"
        "    if not separator:\n"
        "        return False\n"
        "    try:\n"
        "        return hasattr(importlib.import_module(parent), attribute)\n"
        "    except (ImportError, AttributeError, ModuleNotFoundError) as exc:\n"
        "        record_import_error(target, exc)\n"
        "        return False\n"
        "missing = [module for module in modules if not is_importable(module)]\n"
        "if missing:\n"
        "    related = [item for item in import_errors if item.split(':', 1)[0] in missing]\n"
        "    detail = ('; ' + '; '.join(related)) if related else ''\n"
        "    raise AssertionError('missing installed dependency modules: ' + ', '.join(missing) + detail)\n"
    )


def contracts_for_dockerfile(
    contracts: Iterable[ImageContract], dockerfile: Path, target: str | None = None
) -> list[ImageContract]:
    resolved = dockerfile.resolve()
    matches = [contract for contract in contracts if contract.dockerfile.resolve() == resolved]
    if not matches:
        raise ContractError(f"Dockerfile is not registered as a runtime image: {_repository_relative(resolved)}")
    targets = {contract.target for contract in matches}
    if target is not None or len(targets) > 1:
        # One built image is one target; probing it against a sibling target's
        # entrypoints would test the wrong dependency surface.
        matches = [contract for contract in matches if contract.target == target]
        if not matches:
            raise ContractError(
                f"{_repository_relative(resolved)} registers targets {sorted(t or '<last>' for t in targets)}; "
                f"pass --target to smoke one of them (got {target!r})"
            )
    return matches


def contract_for_name(contracts: Iterable[ImageContract], name: str) -> ImageContract:
    matches = [contract for contract in contracts if contract.name == name]
    if not matches:
        raise ContractError(f"runtime image is not registered: {name}")
    return matches[0]


def _docker_run_command(contract: ImageContract, image: str, code: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--entrypoint",
        contract.smoke_python,
        *(item for key, value in contract.smoke_environment for item in ("--env", f"{key}={value}")),
        image,
        "-I",
        "-c",
        code,
    ]


def smoke_image(image: str, contracts: Iterable[ImageContract]) -> int:
    for contract in contracts:
        if contract.dependency_probe_smoke:
            modules = third_party_dependency_modules(contract)
            code = _dependency_probe_code(modules)
            print(
                f"Smoke checking {contract.name}'s {len(modules)} reachable third-party modules in {image}", flush=True
            )
            result = subprocess.run(_docker_run_command(contract, image, code), check=False)
            if result.returncode:
                return result.returncode
        if contract.image_import_smoke:
            for entrypoint in contract.smoke_entrypoints:
                prelude = f"{contract.smoke_prelude}; " if contract.smoke_prelude else ""
                code = (
                    "import importlib, sys; "
                    f"sys.path.insert(0, {contract.workdir.as_posix()!r}); "
                    f"{prelude}"
                    f"importlib.import_module({entrypoint!r})"
                )
                print(f"Smoke importing {contract.name}:{entrypoint} from {image}", flush=True)
                result = subprocess.run(_docker_run_command(contract, image, code), check=False)
                if result.returncode:
                    return result.returncode
        elif not contract.dependency_probe_smoke:
            print(f"Skipping built-image smoke for {contract.name}: registry declares no import-safe probe.")
    return 0


def _release_sha() -> str:
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
        sha = result.stdout.strip() if result.returncode == 0 else ""
    return sha or "unknown"


def build_and_smoke_image(image: str, contract: ImageContract) -> int:
    dockerfile = _repository_relative(contract.dockerfile)
    build_context = _repository_relative(contract.build_context)
    target = ["--target", contract.target] if contract.target else []
    if contract.target:
        # Role targets end with the release stamp; stamp the SHA actually built.
        target += ["--build-arg", f"OMI_RELEASE_SHA={_release_sha()}"]
    build_command = ["docker", "build", "--file", dockerfile, *target, "--tag", image, build_context]
    print(f"Building {contract.name} runtime image: {' '.join(build_command)}", flush=True)
    build = subprocess.run(build_command, check=False)
    if build.returncode:
        return build.returncode
    return smoke_image(image, [contract])


def pull_request_smoke_matrix(contracts: Iterable[ImageContract]) -> str:
    return json.dumps({"service": [contract.name for contract in contracts if contract.pull_request_smoke]})


ROLE_PLATFORMS = {"cloud-run", "cloud-run-job", "gke"}
RELEASE_STAMP_LINES = (
    "ARG OMI_RELEASE_SHA=unknown",
    "ENV OMI_RELEASE_SHA=${OMI_RELEASE_SHA}",
    "LABEL org.opencontainers.image.revision=${OMI_RELEASE_SHA}",
)


def _build_instructions(dockerfile: Path, target: str | None) -> list[str]:
    """Instructions of ``target``'s chain plus every stage it copies from."""
    stage_names = {stage.name for stage in docker_named_stages(dockerfile) if stage.name}
    pending: list[str | None] = [target]
    seen: set[str | None] = set()
    lines: list[str] = []
    while pending:
        stage = pending.pop()
        if stage in seen:
            continue
        seen.add(stage)
        chain = docker_target_instructions(dockerfile, stage)
        lines.extend(chain)
        for line in chain:
            if line.upper().startswith("COPY "):
                for token in shlex.split(line[5:]):
                    if token.startswith("--from=") and token[len("--from=") :] in stage_names:
                        pending.append(token[len("--from=") :])
    return lines


LOCK_INSTALLERS = ("uv pip sync", "pip install", "pip3 install")


def _installs_lock(contract: ImageContract, lock: str) -> bool:
    """True when the image's build copies ``lock`` and a RUN installs from that copy.

    A lock equal to the image Dockerfile means inline pins: some RUN must install.
    """
    lines = _build_instructions(contract.dockerfile, contract.target)
    runs = [line for line in lines if line.upper().startswith("RUN ") and any(i in line for i in LOCK_INSTALLERS)]
    if (REPOSITORY_ROOT / lock).resolve() == contract.dockerfile.resolve():
        return bool(runs)
    name = PurePosixPath(lock).name
    for line in lines:
        if not line.upper().startswith("COPY "):
            continue
        tokens = [token for token in shlex.split(line[5:]) if not token.startswith("--")]
        if len(tokens) < 2 or lock not in tokens[:-1]:
            continue
        destination = tokens[-1]
        if destination.endswith("/") or destination in {".", "./"}:
            destination = posixpath.join(destination, name)
        destination = posixpath.normpath(destination)
        relative = not destination.startswith("/")
        if any(destination in run or (relative and name in run) for run in runs):
            return True
    return False


def _github_texts() -> dict[str, str]:
    """Every workflow and composite action, keyed by repository-relative path."""
    github = REPOSITORY_ROOT / ".github"
    paths = sorted(github.glob("workflows/*.y*ml")) + sorted(github.glob("actions/**/action.y*ml"))
    return {_repository_relative(path): path.read_text(encoding="utf-8") for path in paths}


def _mentions_dockerfile(text: str, relative: str) -> bool:
    # Bounded so backend/Dockerfile does not match backend/Dockerfile.desktop_backend.
    return re.search(rf"{re.escape(relative)}(?![\w.-])", text) is not None


def _names_deploy_target(text: str, name: str) -> bool:
    """True when ``text`` names ``name`` as a deploy target, not as a path segment or prose.

    Accepted forms: a ``service:``/``SERVICE=``-style key whose value is the name, a
    deploy flag (``--service``, ``--gke-service``, ...), a YAML list item, a Cloud Run
    job ``jobId`` assignment or ``/jobs/<name>`` resource, or a ``deploy-<name>.sh``
    script. A bare quoted token or path tail (an image tag, a log filter, a test
    assertion) is not a deploy.
    """
    token = re.escape(name)
    end = r"(?![\w.-])"
    patterns = (
        rf"(?im)^[ \t-]*[\w.-]*service[\w.-]*[ \t]*[:=][ \t]*[\"']?{token}[\"']?[ \t]*(?:#.*)?$",
        rf"--(?:service|gke-service|cloud-run-service|migrate-legacy-public-binding)(?:=|[ \t]+)[\"']?{token}{end}",
        rf"(?m)^[ \t]*-[ \t]+[\"']?{token}[\"']?[ \t]*$",
        rf"(?<![\w.-])jobId[\"']?\]?\s*(?<![=!<>])=\s*[\"']{token}[\"']",
        rf"/jobs/{token}[\"']",
        rf"deploy-{token}\.sh",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def dockerfile_shipped_by_github(dockerfile: Path) -> list[str]:
    """Workflows or composite actions that reference ``dockerfile`` (so it may be shipped)."""
    relative = _repository_relative(dockerfile)
    return [path for path, text in _github_texts().items() if _mentions_dockerfile(text, relative)]


def _deploy_text(path: str) -> str:
    text = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    return _workflow_contract_text(REPOSITORY_ROOT / path) if path.startswith(".github/workflows/") else text


def role_map_errors(contracts: Iterable[ImageContract], registry_path: Path = REGISTRY_PATH) -> list[str]:
    """Check the role -> image -> service map that one train SHA builds from.

    Every service the registry declares (the ``services`` map and every chart in
    ``logging_chart_images``) maps to exactly one role image — a Python role
    image of its role or a native image (``native_images``) of that role; every
    registered image is a role image of exactly one role or carries an
    ``outside_role_split`` reason on its own entry (kept per entry so the map
    never repeats image names that other inventories count).
    """
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    roles = payload.get("roles")
    services = payload.get("services")
    if not isinstance(roles, dict) or not roles:
        return ["runtime-image registry must declare a non-empty roles map"]
    if not isinstance(services, dict) or not services:
        return ["runtime-image registry must declare a non-empty services map"]
    outside = {
        entry["name"]: entry["outside_role_split"]
        for entry in payload.get("images", [])
        if isinstance(entry, dict) and "outside_role_split" in entry
    }
    native_role: dict[str, str | None] = {
        name: spec.get("role") for name, spec in (payload.get("native_images") or {}).items() if isinstance(spec, dict)
    }

    by_name = {contract.name: contract for contract in contracts}
    errors: list[str] = []
    image_role: dict[str, str] = {}
    for role, spec in roles.items():
        images = spec.get("images") if isinstance(spec, dict) else None
        if not isinstance(images, dict) or not images:
            errors.append(f"role {role}: images must map each role image to its dependency lock")
            continue
        for image, lock in images.items():
            if image in image_role:
                errors.append(f"role image {image} belongs to both {image_role[image]} and {role}")
                continue
            image_role[image] = role
            contract = by_name.get(image)
            if contract is None:
                errors.append(f"role {role}: image {image} is not a registered runtime image")
                continue
            if not isinstance(lock, str) or not (REPOSITORY_ROOT / lock).is_file():
                errors.append(f"role {role}: image {image} declares a missing dependency lock {lock!r}")
                continue
            if not _installs_lock(contract, lock):
                errors.append(f"role {role}: image {image} does not install its declared lock {lock}")
            if contract.target is not None:
                chain = docker_target_instructions(contract.dockerfile, contract.target)
                stamp = chain[-len(RELEASE_STAMP_LINES) :]
                early = [line for line in chain[: -len(RELEASE_STAMP_LINES)] if "OMI_RELEASE_SHA" in line]
                if tuple(stamp) != RELEASE_STAMP_LINES or early:
                    errors.append(
                        f"role {role}: target {contract.target} must end with the release stamp "
                        "(ARG/ENV OMI_RELEASE_SHA, LABEL org.opencontainers.image.revision) and reference "
                        "OMI_RELEASE_SHA nowhere earlier, or every later layer rebuilds per SHA"
                    )
                if not contract.dependency_probe_smoke:
                    errors.append(f"role {role}: image {image} must run the dependency probe")

    for name in by_name:
        if name in image_role and name in outside:
            errors.append(f"image {name} is both a role image and outside the role split")
        elif name not in image_role and name not in outside:
            errors.append(f"image {name} is neither a role image nor carries an outside_role_split reason")
    for name, reason in outside.items():
        if not isinstance(reason, str) or not reason:
            errors.append(f"outside_role_split {name}: reason must be a non-empty string")

    served: set[str] = set()
    for service, spec in services.items():
        if not isinstance(spec, dict):
            errors.append(f"service {service}: must be an object")
            continue
        role, image, current = spec.get("role"), spec.get("image"), spec.get("current_image")
        if spec.get("platform") not in ROLE_PLATFORMS:
            errors.append(f"service {service}: platform must be one of {sorted(ROLE_PLATFORMS)}")
        if role not in roles:
            errors.append(f"service {service}: role {role!r} is not declared")
        elif image_role.get(image) != role and native_role.get(image) != role:
            errors.append(f"service {service}: image {image!r} is not a role image of {role}")
        else:
            served.add(image)
        if current not in by_name and current not in native_role:
            errors.append(f"service {service}: current_image {current!r} is not a registered runtime image")
        deploys = spec.get("current_deploy")
        if not isinstance(deploys, list) or not deploys:
            errors.append(f"service {service}: current_deploy must list the files that ship it today")
            continue
        texts: list[str] = []
        for deploy in deploys:
            if not isinstance(deploy, str) or not (REPOSITORY_ROOT / deploy).is_file():
                errors.append(f"service {service}: current_deploy {deploy!r} does not exist")
                continue
            text = _deploy_text(deploy)
            texts.append(text)
            if not _names_deploy_target(text, spec.get("deployed_as", service)):
                errors.append(f"service {service}: current_deploy {deploy} never names the service as a deploy target")
        # A deploy that runs an image another pipeline built (a tag reuse, an admitted image)
        # says so with a reason; otherwise the deploy set must build the current image's Dockerfile.
        elsewhere = spec.get("image_built_elsewhere")
        if elsewhere is not None and (not isinstance(elsewhere, str) or not elsewhere.strip()):
            errors.append(f"service {service}: image_built_elsewhere must be a non-empty reason")
        elif current in native_role and elsewhere is None:
            errors.append(
                f"service {service}: a native current_image needs an image_built_elsewhere reason "
                "(a workflow never builds a native image itself)"
            )
        elif current in by_name and elsewhere is None:
            dockerfile = _repository_relative(by_name[current].dockerfile)
            if texts and not any(_mentions_dockerfile(text, dockerfile) for text in texts):
                errors.append(f"service {service}: no current_deploy builds {current}'s {dockerfile}")

    for contract in by_name.values():
        if not contract.build_only:
            continue
        users = sorted(name for name, spec in services.items() if spec.get("current_image") == contract.name)
        if users:
            errors.append(f"build_only image {contract.name} is the current image of {users}")
        shippers = dockerfile_shipped_by_github(contract.dockerfile)
        if shippers:
            errors.append(
                f"build_only image {contract.name}: {_repository_relative(contract.dockerfile)} "
                f"is referenced by {shippers}; clear build_only and register the deploy"
            )

    for chart, image in payload.get("logging_chart_images", {}).items():
        spec = services.get(chart)
        if not isinstance(spec, dict):
            errors.append(f"chart {chart} has no role-image service entry")
        elif spec.get("current_image") != image:
            errors.append(f"service {chart}: current_image {spec.get('current_image')!r} != chart image {image!r}")
    for image in sorted(set(image_role) - served):
        errors.append(f"role image {image} serves no declared service")
    for image in sorted(set(native_role) - served):
        errors.append(f"native image {image} serves no declared service")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="check registered source-closure and deployment-workflow contracts")
    subparsers.add_parser("check-source", help="check each entrypoint's first-party Docker source closure")
    subparsers.add_parser("check-workflows", help="check registered deployment workflows smoke their image")
    subparsers.add_parser("check-roles", help="check the role -> image -> service map and role-image build stamps")
    smoke = subparsers.add_parser("smoke", help="import an already-built image's registered entrypoint")
    smoke.add_argument("--dockerfile", type=Path, required=True)
    smoke.add_argument("--image", required=True)
    smoke.add_argument("--target", help="build stage of a multi-target Dockerfile the image was built from")
    build_smoke = subparsers.add_parser("build-smoke", help="build one registered image then import its entrypoint")
    build_smoke.add_argument("--service", required=True)
    build_smoke.add_argument("--image", required=True)
    subparsers.add_parser("pull-request-matrix", help="emit the registered pull-request image-smoke matrix as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "smoke":
            dockerfile = args.dockerfile
            if not dockerfile.is_absolute():
                dockerfile = REPOSITORY_ROOT / dockerfile
            contracts = load_contracts(args.registry, dockerfile_filter=dockerfile)
        else:
            dockerfile = None
            contracts = load_contracts(args.registry)
        if args.command in {"check", "check-source", "check-workflows", "check-roles"}:
            errors = []
            if args.command in {"check", "check-source"}:
                errors.extend(check_source_closures(contracts))
                errors.extend(import_smoke_environment_errors(contracts))
            if args.command in {"check", "check-workflows"}:
                errors.extend(workflow_contract_errors(contracts))
            if args.command in {"check", "check-roles"}:
                errors.extend(role_map_errors(contracts, args.registry))
            if errors:
                print("FAIL: runtime-image contract is incomplete:", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print(f"Runtime-image contracts passed for {len(contracts)} registered images.")
            return 0
        if args.command == "build-smoke":
            return build_and_smoke_image(args.image, contract_for_name(contracts, args.service))
        if args.command == "pull-request-matrix":
            print(pull_request_smoke_matrix(contracts))
            return 0
        assert dockerfile is not None  # reached only for the smoke command
        return smoke_image(args.image, contracts_for_dockerfile(contracts, dockerfile, args.target))
    except ContractError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
