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
IGNORED_SOURCE_DIRECTORIES = {".git", ".pytest_cache", ".venv", "__pycache__"}


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


@dataclass(frozen=True)
class CopyInstruction:
    sources: tuple[str, ...]
    destination: str


class ContractError(ValueError):
    """Raised when the registry or a Dockerfile cannot define a deterministic contract."""


def _repository_relative(path: Path) -> str:
    return path.relative_to(REPOSITORY_ROOT).as_posix()


def load_contracts(registry_path: Path = REGISTRY_PATH) -> list[ImageContract]:
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
        deployment_workflows_raw = entry.get("deployment_workflows")
        if (
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


def final_stage_copy_instructions(dockerfile: Path) -> list[CopyInstruction]:
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

    copies: list[CopyInstruction] = []
    for line in stages[-1]:
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
    for instruction in final_stage_copy_instructions(contract.dockerfile):
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


def check_source_closures(contracts: Iterable[ImageContract]) -> list[str]:
    errors: list[str] = []
    for contract in contracts:
        errors.extend(source_closure_errors(contract))
    return errors


def workflow_contract_errors(contracts: Iterable[ImageContract]) -> list[str]:
    errors: list[str] = []
    for contract in contracts:
        dockerfile = _repository_relative(contract.dockerfile)
        for workflow in contract.deployment_workflows:
            workflow_text = workflow.read_text(encoding="utf-8")
            workflow_name = _repository_relative(workflow)
            if not any(
                marker in workflow_text
                for marker in ("runtime_image_contracts.py smoke", 'runtime_image_contracts.py" smoke')
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
    """Return an offline probe for module paths and ``from`` import attributes."""
    return (
        "import importlib, importlib.util\n"
        f"modules = {list(modules)!r}\n"
        "def is_importable(target):\n"
        "    try:\n"
        "        if importlib.util.find_spec(target) is not None:\n"
        "            return True\n"
        "    except (ImportError, AttributeError, ModuleNotFoundError):\n"
        "        pass\n"
        "    parent, separator, attribute = target.rpartition('.')\n"
        "    if not separator:\n"
        "        return False\n"
        "    try:\n"
        "        return hasattr(importlib.import_module(parent), attribute)\n"
        "    except (ImportError, AttributeError, ModuleNotFoundError):\n"
        "        return False\n"
        "missing = [module for module in modules if not is_importable(module)]\n"
        "assert not missing, f'missing installed dependency modules: {missing}'"
    )


def contracts_for_dockerfile(contracts: Iterable[ImageContract], dockerfile: Path) -> list[ImageContract]:
    resolved = dockerfile.resolve()
    matches = [contract for contract in contracts if contract.dockerfile.resolve() == resolved]
    if not matches:
        raise ContractError(f"Dockerfile is not registered as a runtime image: {_repository_relative(resolved)}")
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


def build_and_smoke_image(image: str, contract: ImageContract) -> int:
    dockerfile = _repository_relative(contract.dockerfile)
    build_context = _repository_relative(contract.build_context)
    build_command = ["docker", "build", "--file", dockerfile, "--tag", image, build_context]
    print(f"Building {contract.name} runtime image: {' '.join(build_command)}", flush=True)
    build = subprocess.run(build_command, check=False)
    if build.returncode:
        return build.returncode
    return smoke_image(image, [contract])


def pull_request_smoke_matrix(contracts: Iterable[ImageContract]) -> str:
    return json.dumps({"service": [contract.name for contract in contracts if contract.pull_request_smoke]})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="check registered source-closure and deployment-workflow contracts")
    subparsers.add_parser("check-source", help="check each entrypoint's first-party Docker source closure")
    subparsers.add_parser("check-workflows", help="check registered deployment workflows smoke their image")
    smoke = subparsers.add_parser("smoke", help="import an already-built image's registered entrypoint")
    smoke.add_argument("--dockerfile", type=Path, required=True)
    smoke.add_argument("--image", required=True)
    build_smoke = subparsers.add_parser("build-smoke", help="build one registered image then import its entrypoint")
    build_smoke.add_argument("--service", required=True)
    build_smoke.add_argument("--image", required=True)
    subparsers.add_parser("pull-request-matrix", help="emit the registered pull-request image-smoke matrix as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        contracts = load_contracts(args.registry)
        if args.command in {"check", "check-source", "check-workflows"}:
            errors = []
            if args.command in {"check", "check-source"}:
                errors.extend(check_source_closures(contracts))
            if args.command in {"check", "check-workflows"}:
                errors.extend(workflow_contract_errors(contracts))
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
        dockerfile = args.dockerfile
        if not dockerfile.is_absolute():
            dockerfile = REPOSITORY_ROOT / dockerfile
        return smoke_image(args.image, contracts_for_dockerfile(contracts, dockerfile))
    except ContractError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
