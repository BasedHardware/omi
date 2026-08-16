"""Import hierarchy ratchet: utils/* must never import routers/*.

The backend import hierarchy is database/ → utils/ → routers/ → main.py.
A utils module that imports routers creates upward coupling and circular-import risk.
This AST scan fails while any utils module still references routers.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
UTILS_DIR = BACKEND_DIR / "utils"


def _utils_python_files():
    for path in sorted(UTILS_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def _router_imports_in_file(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("routers"):
            offenders.append((node.lineno, f"from {node.module} import ..."))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "routers" or alias.name.startswith("routers."):
                    offenders.append((node.lineno, f"import {alias.name}"))
    return offenders


def test_utils_modules_do_not_import_routers():
    violations: list[str] = []
    for path in _utils_python_files():
        rel = path.relative_to(BACKEND_DIR)
        for lineno, detail in _router_imports_in_file(path):
            violations.append(f"{rel}:{lineno} {detail}")
    assert not violations, "utils must not import routers:\n" + "\n".join(violations)
