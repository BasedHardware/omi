from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_mcp_oauth_deploy_contract.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_mcp_oauth_deploy_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_prod_mcp_oauth_deploy_contract_is_wired():
    checker = load_checker()
    assert checker.validate_mcp_oauth_deploy_contract() == []
