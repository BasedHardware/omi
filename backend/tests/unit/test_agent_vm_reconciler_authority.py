"""User-facing Agent VM paths may request, but never bypass, reconciliation."""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _function(path: Path, name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
    assert len(matches) == 1
    return matches[0]


def _called_names(node: ast.AST) -> set[str]:
    return {call.func.id for call in ast.walk(node) if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)}


def _run_blocking_targets(node: ast.AST) -> set[str]:
    targets = set()
    for call in ast.walk(node):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "run_blocking"
            and len(call.args) >= 2
        ):
            continue
        target = call.args[1]
        if isinstance(target, ast.Name):
            targets.add(target.id)
    return targets


def test_proxy_and_tools_have_no_direct_compute_control_plane_path():
    for relative_path in ("agent-proxy/main.py", "routers/agent_tools.py"):
        source = (BACKEND_DIR / relative_path).read_text(encoding="utf-8")
        assert "compute.googleapis.com" not in source
        assert "request_vm_start" in source


def test_desktop_status_requests_reconciliation_without_direct_power_mutation():
    status = _function(BACKEND_DIR / "routers/desktop_agent_vm.py", "get_agent_status")
    calls = _called_names(status)
    blocking_targets = _run_blocking_targets(status)

    assert "request_vm_start" in blocking_targets
    assert not {"_start_vm", "_stop_vm", "_set_service_account", "_delete_vm"} & calls
