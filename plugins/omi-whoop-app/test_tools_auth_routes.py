import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from fastapi.testclient import TestClient
from whoop_tools_auth import require_whoop_tools_auth

TOOL_ROUTES = (
    "/tools/get_recovery",
    "/tools/get_strain",
    "/tools/get_sleep",
    "/tools/get_workouts",
    "/tools/get_weekly_summary",
    "/tools/get_body_measurements",
    "/tools/get_profile",
)


def test_all_sensitive_tool_routes_are_guarded(monkeypatch):
    monkeypatch.delenv("WHOOP_TOOLS_SECRET", raising=False)
    client = TestClient(main.app)

    for route in TOOL_ROUTES:
        response = client.post(route, json={"uid": "victim-connected-whoop-account"})

        assert response.status_code == 503, (
            f"{route} is missing require_whoop_tools_auth or does not fail closed"
        )


def test_existing_handler_tests_can_bypass_only_the_guard():
    main.app.dependency_overrides[require_whoop_tools_auth] = lambda: None

    try:
        assert main.app.dependency_overrides[require_whoop_tools_auth]() is None
    finally:
        main.app.dependency_overrides.clear()

    assert require_whoop_tools_auth not in main.app.dependency_overrides
