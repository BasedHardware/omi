from __future__ import annotations

from pathlib import Path
from packaging.requirements import Requirement

ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"
REQUIREMENTS_PATH = ROOT_DIR / "requirements.txt"

PYOBJC_PACKAGES = {
    "pyobjc-core",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-CoreBluetooth",
    "pyobjc-framework-libdispatch",
}


def _read_pyproject_dependencies() -> list[Requirement]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    with open(PYPROJECT_PATH, "rb") as f:
        data = tomllib.load(f)

    deps = data.get("project", {}).get("dependencies", [])
    return [Requirement(dep) for dep in deps]


def _read_requirements_dependencies() -> list[Requirement]:
    lines = REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
    reqs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        reqs.append(Requirement(line))
    return reqs


def test_pyproject_pyobjc_have_darwin_marker():
    reqs = _read_pyproject_dependencies()
    pyobjc_reqs = [r for r in reqs if r.name in PYOBJC_PACKAGES]
    assert len(pyobjc_reqs) == 4, f"Expected 4 pyobjc dependencies, got {len(pyobjc_reqs)}"

    for req in pyobjc_reqs:
        assert req.marker is not None, f"{req.name} has no environment marker"
        assert req.marker.evaluate({"sys_platform": "darwin"}) is True
        assert req.marker.evaluate({"sys_platform": "linux"}) is False
        assert req.marker.evaluate({"sys_platform": "win32"}) is False


def test_requirements_txt_pyobjc_have_darwin_marker():
    reqs = _read_requirements_dependencies()
    pyobjc_reqs = [r for r in reqs if r.name in PYOBJC_PACKAGES]
    assert len(pyobjc_reqs) == 4, f"Expected 4 pyobjc dependencies, got {len(pyobjc_reqs)}"

    for req in pyobjc_reqs:
        assert req.marker is not None, f"{req.name} has no environment marker"
        assert req.marker.evaluate({"sys_platform": "darwin"}) is True
        assert req.marker.evaluate({"sys_platform": "linux"}) is False
        assert req.marker.evaluate({"sys_platform": "win32"}) is False


def test_cross_platform_dependencies_selected_everywhere():
    for get_reqs in (_read_pyproject_dependencies, _read_requirements_dependencies):
        reqs = get_reqs()
        common_pkgs = {"bleak", "opuslib", "websockets"}
        common_reqs = [r for r in reqs if r.name in common_pkgs]
        assert len(common_reqs) == len(common_pkgs)

        for platform in ("linux", "win32", "darwin"):
            active_names = {
                r.name for r in reqs
                if r.marker is None or r.marker.evaluate({"sys_platform": platform})
            }
            # Common dependencies must be active everywhere
            for pkg in common_pkgs:
                assert pkg in active_names, f"{pkg} missing on {platform}"

            # PyObjC dependencies must only be active on darwin
            if platform == "darwin":
                assert PYOBJC_PACKAGES.issubset(active_names)
            else:
                assert not PYOBJC_PACKAGES.intersection(active_names)
