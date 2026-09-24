"""Smoke test script for Omi Solana Pay app."""

import sys
from fastapi.testclient import TestClient
from main import app

def run_smoke_test():
    print("=== Running Omi Solana Pay Smoke Test ===")
    client = TestClient(app)

    # 1. Health
    r = client.get("/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print("  [PASS] /health")

    # 2. Manifest
    r = client.get("/.well-known/omi-tools.json")
    assert r.status_code == 200, f"Manifest failed: {r.status_code}"
    tools = r.json().get("tools", [])
    assert len(tools) >= 4, f"Expected at least 4 tools, got {len(tools)}"
    print(f"  [PASS] /.well-known/omi-tools.json ({len(tools)} tools verified)")

    # 3. Parse Solana Pay URL
    test_url = "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=2.50&label=Omi%20Kiosk&memo=Invoice%23992"
    r = client.post("/tools/parse_solana_pay_request", json={"solana_pay_url": test_url})
    assert r.status_code == 200, f"Parse failed: {r.status_code}"
    res = r.json()
    assert res.get("error") is None, f"Parse returned error: {res.get('error')}"
    assert res.get("data", {}).get("amount") == 2.50
    assert "Omi Kiosk" in res.get("data", {}).get("label")
    print("  [PASS] /tools/parse_solana_pay_request")

    # 4. Generate Speech Dialogue
    r = client.post("/tools/generate_payment_intent", json={
        "recipient": "Omi Kiosk",
        "amount": 2.50,
        "currency": "USDC",
        "memo": "Invoice#992"
    })
    assert r.status_code == 200
    res = r.json()
    assert res.get("error") is None
    assert "Confirm" in res.get("result", "")
    print("  [PASS] /tools/generate_payment_intent")

    # 5. Invalid Input Guard
    r = client.post("/tools/check_solana_balance", json={"wallet_address": "invalid_format!"})
    assert r.status_code == 200
    assert r.json().get("error") is not None
    print("  [PASS] /tools/check_solana_balance input validation guard")

    # 6. Invalid Network Guard
    r = client.post("/tools/check_solana_balance", json={"wallet_address": "FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8", "network": "testnet"})
    assert r.status_code == 200
    assert "Invalid network" in r.json().get("error", "")
    print("  [PASS] /tools/check_solana_balance network validation guard")

    print("\n[ALL PASSED] All Omi Solana Pay Smoke Tests Passed Successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(run_smoke_test())

