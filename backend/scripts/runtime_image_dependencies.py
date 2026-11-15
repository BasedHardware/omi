#!/usr/bin/env python3
"""Offline third-party closure for registered runtime images.

Owns ``runtime_image_contracts.py check-third-party``: every third-party import
reachable from an image's entrypoints must map to a distribution that the image's
own closed lock installs (a pylock, or a resolver-compiled requirements list).
The full backend lock that unit tests sync cannot stand in for a per-image lock;
#24490/#24366 shipped a worker image without deepgram-sdk and langdetect that
way. Open dependency sets (ranges, path or URL installs, hand-pinned lists) are
reported, never judged: a module there may arrive transitively.
"""

from __future__ import annotations

import ast
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from runtime_image_contracts import (
    LOCK_INSTALLERS,
    ContractError,
    ImageContract,
    _repository_relative,
    docker_named_stages,
    docker_target_instructions,
    third_party_dependency_modules,
)

# Import name -> distribution, for the third-party closure check, where the
# distribution's normalized name is not the import path. Dotted keys match the
# longest import prefix first, so ``google.cloud.firestore`` needs no entry
# (it normalizes to ``google-cloud-firestore``) while ``google.protobuf``
# does. ``None`` marks a bare namespace package: it is skipped only when it is
# the whole import path, so an unmapped submodule under it still fails.
MODULE_DISTRIBUTIONS: dict[str, str | None] = {
    "PIL": "pillow",
    "deepgram": "deepgram-sdk",
    "dotenv": "python-dotenv",
    "google": None,
    "google.cloud": None,
    "google.cloud.exceptions": "google-cloud-core",
    "google.oauth2": "google-auth",
    "google.protobuf": "protobuf",
    "google.rpc": "googleapis-common-protos",
    "grpc": "grpcio",
    "jwt": "pyjwt",
    "lc3": "lc3py",
    "markdown_it": "markdown-it-py",
    "multipart": "python-multipart",
    "nemo": "nemo-toolkit",
    "pyannote": None,
    "ulid": "python-ulid",
    "yaml": "pyyaml",
}
# Standard library on the images' Python 3.11 but absent from newer local
# interpreters' ``sys.stdlib_module_names`` (PEP 594 removals).
IMAGE_STDLIB_MODULES = frozenset({"audioop"})
# ``google.cloud.tasks_v2`` ships in ``google-cloud-tasks``: an API version
# suffix is not part of the distribution name.
_API_VERSION_SUFFIX = re.compile(r"_v\d+(?:(?:alpha|beta|p)\d*)*$")
# The interpreter and platform every registered image runs, for lock markers.
_IMAGE_MARKER_ENVIRONMENT = {
    "implementation_name": "cpython",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_system": "Linux",
    "python_full_version": "3.11",  # patch floats with the base tag; see marker_applies_to_image
    "python_version": "3.11",
    "sys_platform": "linux",
}
_MARKER_COMPARISON = re.compile(r"""(\w+)\s*(===|==|!=|<=|>=|~=|<|>|not in|in)\s*(['"])(.*?)\3""")
# Options of ``pip install`` / ``uv pip sync`` that consume the next token.
_INSTALLER_VALUE_OPTIONS = frozenset(
    {
        "-c", "--constraint", "-i", "--index-url", "--extra-index-url", "-f", "--find-links",
        "-p", "--python", "-t", "--target", "--prefix", "--root", "--cache-dir", "--trusted-host",
    }
)  # fmt: skip
_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class InstalledDependencies:
    """Distributions a Dockerfile installs, and whether that set is closed.

    A pylock or a requirements set pinned entirely with ``==`` lists every
    transitive distribution, so an absent name is really absent from the
    image. Any range specifier, path install or unresolvable file leaves the
    set open: a module might arrive transitively, so the check cannot judge it.
    """

    sources: tuple[str, ...]
    distributions: frozenset[str]
    open_reasons: tuple[str, ...]


def normalize_distribution(name: str) -> str:
    """PEP 503 normalization: ``Deepgram_SDK`` and ``deepgram.sdk`` are ``deepgram-sdk``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_tuple(value: str) -> tuple[int, ...] | None:
    parts = value.split(".")
    return tuple(int(part) for part in parts) if all(part.isdigit() for part in parts) else None


def _compare_versions(actual: str, operator: str, expected: str) -> bool | None:
    left, right = _version_tuple(actual), _version_tuple(expected)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    left, right = left + (0,) * (width - len(left)), right + (0,) * (width - len(right))
    return {
        "==": left == right,
        "!=": left != right,
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
    }.get(operator)


def marker_applies_to_image(marker: str) -> bool:
    """Evaluate a PEP 508 marker for the images' Linux x86_64 CPython 3.11.

    Anything this small evaluator cannot decide counts as not applying, so a
    conditional distribution can only ever be left out of the installed set,
    never credited to it.
    """
    undecidable = False

    def compare(match: re.Match[str]) -> str:
        nonlocal undecidable
        variable, operator, _, expected = match.groups()
        actual = _IMAGE_MARKER_ENVIRONMENT.get(variable)
        if actual is None:
            undecidable = True
            return "False"
        if variable == "python_full_version":
            # Base tags float on the patch (3.11-slim): decide only comparisons
            # every 3.11.x answers alike. A comparison against X.Y.Z can only
            # change answer at Z, so patch 0, Z-1, Z, Z+1 and a large patch
            # cover every region of the range.
            parts = expected.split(".")
            boundary = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            patches = {0, 9999, boundary, max(boundary - 1, 0), boundary + 1}
            outcomes = {_compare_versions(f"3.11.{patch}", operator, expected) for patch in patches}
            if len(outcomes) != 1 or None in outcomes:
                undecidable = True
                return "False"
            return str(outcomes.pop())
        if variable.endswith("_version") and operator in {"<", "<=", ">", ">=", "==", "!="}:
            left, right = _version_tuple(actual), _version_tuple(expected)
            if left is None or right is None:
                undecidable = True
                return "False"
            width = max(len(left), len(right))
            left, right = left + (0,) * (width - len(left)), right + (0,) * (width - len(right))
        else:
            left, right = actual, expected
        result = {
            "==": left == right,
            "===": left == right,
            "!=": left != right,
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
            "in": isinstance(left, str) and left in right,
            "not in": isinstance(left, str) and left not in right,
        }.get(operator)
        if result is None:
            undecidable = True
            return "False"
        return str(result)

    expression = _MARKER_COMPARISON.sub(compare, marker)
    if undecidable or not re.fullmatch(r"(?:\s|\(|\)|True|False|and|or|not)*", expression):
        return False
    return bool(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 - only True/False/and/or/not/parens remain


def _pylock_distributions(path: Path) -> set[str]:
    import tomllib

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"cannot read lock {_repository_relative(path)}: {exc}") from exc
    return {
        normalize_distribution(package["name"])
        for package in payload.get("packages", [])
        if "name" in package and ("marker" not in package or marker_applies_to_image(package["marker"]))
    }


# A requirements file lists every transitive distribution only when a resolver
# wrote it; a hand-maintained list pinned with ``==`` can still omit one.
_COMPILED_REQUIREMENTS_HEADERS = ("autogenerated by pip-compile", "autogenerated by uv via")


def _requirement_distributions(path: Path, seen: set[Path] | None = None) -> tuple[set[str], list[str]]:
    """Names in a requirements file (following ``-r``) and the reasons it is open."""
    seen = set() if seen is None else seen
    resolved = path.resolve()
    if resolved in seen:
        return set(), []
    seen.add(resolved)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read requirements {_repository_relative(path)}: {exc}") from exc
    names: set[str] = set()
    open_reasons: list[str] = []
    relative = _repository_relative(path)
    header = text[:2000].lower()
    pinned_lines = 0
    for raw in text.replace("\\\n", " ").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-r", "--requirement=")):
            include = re.sub(r"^(-r|--requirement)[ =]?", "", line).strip()
            included, reasons = _requirement_distributions(path.parent / include, seen)
            names |= included
            open_reasons.extend(reasons)
            continue
        if line.startswith("-"):
            if line.startswith(("-e", "--editable")):
                open_reasons.append(f"{relative}: editable install {line}")
            continue
        match = _REQUIREMENT_NAME.match(line)
        if match is None or line.startswith((".", "/")):
            open_reasons.append(f"{relative}: path install {line}")
            continue
        requirement, _, marker = line.partition(";")
        if marker.strip() and not marker_applies_to_image(marker.strip()):
            continue
        names.add(normalize_distribution(match.group(1)))
        specifier = requirement[match.end() :]
        if " @ " in requirement or "@" in specifier:
            open_reasons.append(f"{relative}: direct reference {line}")
        elif "==" not in specifier:
            open_reasons.append(f"{relative}: unpinned {line}")
        else:
            pinned_lines += 1
    if pinned_lines and not any(marker in header for marker in _COMPILED_REQUIREMENTS_HEADERS):
        open_reasons.append(f"{relative}: pinned by hand, not a resolver-compiled list")
    return names, open_reasons


def _installer_arguments(command: str) -> tuple[list[str], list[str]] | None:
    """(requirement files, inline requirements) for one installer shell command."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for index in range(len(tokens) - 1):
        if tokens[index : index + 2] == ["pip", "install"] or tokens[index : index + 2] == ["pip3", "install"]:
            arguments, sync = tokens[index + 2 :], False
            break
        if tokens[index : index + 3] == ["uv", "pip", "sync"]:
            arguments, sync = tokens[index + 3 :], True
            break
    else:
        return None
    files: list[str] = []
    inline: list[str] = []
    position = 0
    while position < len(arguments):
        token = arguments[position]
        if token in {"-r", "--requirement"} and position + 1 < len(arguments):
            files.append(arguments[position + 1])
            position += 2
            continue
        if token.startswith("--requirement="):
            files.append(token.split("=", 1)[1])
        elif token in _INSTALLER_VALUE_OPTIONS:
            position += 1
        elif not token.startswith("-"):
            (files if sync else inline).append(token)
        position += 1
    return files, inline


def installed_dependencies(contract: ImageContract) -> InstalledDependencies:
    """Resolve the distributions every installer RUN of the image's build installs.

    Each stage chain is walked in build order so a relative COPY or install
    path resolves against the WORKDIR in force; an installed file is traced
    back through the COPY that put it there to its repository source.
    """
    stage_names = {stage.name for stage in docker_named_stages(contract.dockerfile) if stage.name}
    # (stage, copied environment paths): None credits every install of the
    # image's own chain; a copied-from stage credits only installs that target
    # an environment the image copies out of it.
    pending: list[tuple[str | None, tuple[str, ...] | None]] = [(contract.target, None)]
    seen_stages: set[tuple[str | None, tuple[str, ...] | None]] = set()
    sources: list[str] = []
    distributions: set[str] = set()
    open_reasons: list[str] = []
    while pending:
        stage, environments = pending.pop()
        if (stage, environments) in seen_stages:
            continue
        seen_stages.add((stage, environments))
        workdir = PurePosixPath("/")
        active: set[str] = set()  # copied environments activated by ENV PATH / VIRTUAL_ENV
        copied: list[tuple[PurePosixPath, Path, bool]] = []  # (destination, source, destination is a directory)
        for line in docker_target_instructions(contract.dockerfile, stage):
            keyword = line.split(None, 1)[0].upper()
            if keyword == "WORKDIR":
                workdir = workdir / line.split(None, 1)[1].strip()
                continue
            if keyword == "ENV" and environments:
                active |= {
                    path
                    for path in environments
                    if f"{path}/bin" in line or re.search(rf"VIRTUAL_ENV[= ]+[\"']?{re.escape(path)}\b", line)
                }
                continue
            if keyword == "COPY":
                tokens = shlex.split(line[5:])
                from_stage = next((token[len("--from=") :] for token in tokens if token.startswith("--from=")), None)
                if from_stage is not None:
                    # Only an environment copy carries a stage's installed
                    # distributions; a copied binary or asset does not.
                    copied_environments = tuple(
                        sorted(
                            source.rstrip("/")
                            for source in [token for token in tokens if not token.startswith("--")][:-1]
                            if "venv" in source or "site-packages" in source or "dist-packages" in source
                        )
                    )
                    if from_stage in stage_names and copied_environments:
                        pending.append((from_stage, copied_environments))
                    continue
                tokens = [token for token in tokens if not token.startswith("--")]
                if len(tokens) < 2:
                    continue
                destination = workdir / tokens[-1]
                into_directory = tokens[-1].endswith("/") or tokens[-1] in {".", "./"} or len(tokens) > 2
                for source in tokens[:-1]:
                    source_path = (contract.build_context / source).resolve()
                    is_directory = into_directory or source_path.is_dir()
                    copied.append((destination, source_path, is_directory))
                continue
            if keyword != "RUN" or not any(installer in line for installer in LOCK_INSTALLERS):
                continue
            for command in re.split(r"&&|;|\|\|", line[4:]):
                parsed = _installer_arguments(command)
                if parsed is None:
                    continue
                if environments is not None and not (active or any(path in command for path in environments)):
                    continue  # installs into an interpreter the image does not copy
                files, inline = parsed
                for requirement in inline:
                    match = _REQUIREMENT_NAME.match(requirement)
                    if match is None:
                        open_reasons.append(f"inline install {requirement}")
                        continue
                    distributions.add(normalize_distribution(match.group(1)))
                    specifier = requirement[match.end() :]
                    if " @ " in requirement or "@" in specifier:
                        open_reasons.append(f"inline direct reference {requirement}")
                    elif "==" not in specifier:
                        open_reasons.append(f"inline unpinned install {requirement}")
                for installed in files:
                    target = workdir / installed
                    source = None
                    for destination, source_path, is_directory in reversed(copied):
                        if is_directory and target.is_relative_to(destination):
                            candidate = source_path / target.relative_to(destination)
                            if source_path.is_dir() and candidate.is_file():
                                source = candidate
                            elif not source_path.is_dir() and target == destination / source_path.name:
                                source = source_path
                        elif not is_directory and target == destination:
                            source = source_path
                        if source is not None:
                            break
                    if source is None:
                        open_reasons.append(f"cannot trace installed file {installed} to a COPY source")
                        continue
                    source = source.resolve()
                    sources.append(_repository_relative(source))
                    if source.suffix == ".toml":
                        distributions |= _pylock_distributions(source)
                    else:
                        names, reasons = _requirement_distributions(source)
                        distributions |= names
                        open_reasons.extend(reasons)
    if not sources and not distributions:
        open_reasons.append("no dependency installer found")
    return InstalledDependencies(
        sources=tuple(dict.fromkeys(sources)),
        distributions=frozenset(distributions),
        open_reasons=tuple(dict.fromkeys(open_reasons)),
    )


def module_distribution_candidates(module: str) -> tuple[str, ...] | None:
    """Distributions that may provide ``module``.

    An explicit ``MODULE_DISTRIBUTIONS`` entry for the longest matching prefix
    is authoritative. Otherwise an ordinary package is owned by its top-level
    name's distribution, so ``fastapi.FastAPI`` can only be ``fastapi``. Under
    a namespace package (a ``None`` entry such as ``google``) only the provider
    component right below the namespace levels names the distribution, with an
    API-version suffix dropped (``google.cloud.tasks_v2`` -> ``google-cloud-tasks``). Returns
    ``None`` when ``module`` is itself a bare namespace package, which no
    single distribution owns.
    """
    if MODULE_DISTRIBUTIONS.get(module, "") is None or module in IMAGE_STDLIB_MODULES:
        return None
    parts = module.split(".")
    prefixes = [".".join(parts[:length]) for length in range(len(parts), 0, -1)]
    for prefix in prefixes:
        mapped = MODULE_DISTRIBUTIONS.get(prefix, "")
        if mapped:
            return (normalize_distribution(mapped),)
    if MODULE_DISTRIBUTIONS.get(parts[0], "") is not None:
        return (normalize_distribution(parts[0]),)
    # The provider is the first component below the namespace levels:
    # google.cloud.tasks_v2.X belongs to google-cloud-tasks(-v2), never to a
    # distribution named after a deeper submodule.
    depth = 1
    while depth < len(parts) and MODULE_DISTRIBUTIONS.get(".".join(parts[: depth + 1]), "") is None:
        depth += 1
    if depth >= len(parts):
        return None
    provider = ".".join(parts[: depth + 1])
    candidates = [normalize_distribution(provider)]
    unversioned = _API_VERSION_SUFFIX.sub("", provider)
    if unversioned != provider:
        candidates.append(normalize_distribution(unversioned))
    return tuple(dict.fromkeys(candidates))


def third_party_closure_errors(
    contract: ImageContract, *, _trees: dict[Path, ast.Module] | None = None
) -> tuple[list[str], InstalledDependencies]:
    """Every reachable third-party import must map to a distribution the image installs."""
    installed = installed_dependencies(contract)
    if installed.open_reasons:
        return [], installed
    missing: list[str] = []
    for module in third_party_dependency_modules(contract, _trees=_trees):
        candidates = module_distribution_candidates(module)
        if candidates is None or any(candidate in installed.distributions for candidate in candidates):
            continue
        missing.append(module)
    if not missing:
        return [], installed
    tops = sorted({module.split(".", 1)[0] for module in missing})
    return [
        f"{contract.name}: reachable third-party imports {', '.join(tops)} map to no distribution installed by "
        f"{', '.join(installed.sources)} ({', '.join(missing[:8])}{' ...' if len(missing) > 8 else ''}); "
        "add the distribution to that lock, or map the import name in MODULE_DISTRIBUTIONS"
    ], installed


def check_third_party_closures(contracts: Iterable[ImageContract]) -> tuple[list[str], list[str]]:
    """(errors, notes): notes name images whose open dependency set is not judged."""
    errors: list[str] = []
    notes: list[str] = []
    trees: dict[Path, ast.Module] = {}
    for contract in contracts:
        contract_errors, installed = third_party_closure_errors(contract, _trees=trees)
        errors.extend(contract_errors)
        if installed.open_reasons:
            notes.append(
                f"{contract.name}: third-party closure not checked, open dependency set ({installed.open_reasons[0]})"
            )
    return errors, notes
