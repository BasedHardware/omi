import asyncio
from pathlib import Path
from types import ModuleType
from typing import Any

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def test_auto_sync_action_item_sanitizes_exception_leak() -> None:
    def failing_get_default(_uid: str):
        raise RuntimeError("INTERNAL_DATABASE_CREDENTIALS_LEAK")

    stubs = {
        "database.users": _module(
            "database.users",
            get_default_task_integration=failing_get_default,
            get_task_integration=lambda _u, _a: {"connected": True},
        ),
        "database.action_items": _module(
            "database.action_items",
            get_action_item=lambda *_a, **_k: None,
            update_action_item=lambda *_a, **_k: None,
            batch_set_sync_requested=lambda *_a, **_k: None,
        ),
        "utils.notifications": _module(
            "utils.notifications",
            send_apple_reminders_sync_push_async=lambda **_k: None,
        ),
        "utils.task_integrations_ops": _module(
            "utils.task_integrations_ops",
            create_task_internal=lambda **_k: {"success": True},
        ),
    }

    with stub_modules(stubs):
        task_sync = load_module_fresh("utils.task_sync", str(BACKEND_DIR / "utils" / "task_sync.py"))
        result = asyncio.run(task_sync.auto_sync_action_item("user-123", {"id": "item-1", "description": "Buy milk"}))

    assert result["synced"] is False
    assert result["error"] == "Auto-sync failed"
    assert "INTERNAL_DATABASE_CREDENTIALS_LEAK" not in str(result)


def test_auto_sync_action_items_batch_sanitizes_exception_leak() -> None:
    def failing_get_default(_uid: str):
        raise RuntimeError("INTERNAL_REDIS_AUTH_SECRET_LEAK")

    stubs = {
        "database.users": _module(
            "database.users",
            get_default_task_integration=failing_get_default,
            get_task_integration=lambda _u, _a: {"connected": True},
        ),
        "database.action_items": _module(
            "database.action_items",
            get_action_item=lambda *_a, **_k: None,
            update_action_item=lambda *_a, **_k: None,
            batch_set_sync_requested=lambda *_a, **_k: None,
        ),
        "utils.notifications": _module(
            "utils.notifications",
            send_apple_reminders_sync_push_async=lambda **_k: None,
        ),
        "utils.task_integrations_ops": _module(
            "utils.task_integrations_ops",
            create_task_internal=lambda **_k: {"success": True},
        ),
    }

    items = [
        {"id": "item-1", "description": "Review PRs"},
        {"id": "item-2", "description": "Deploy fix"},
    ]

    with stub_modules(stubs):
        task_sync = load_module_fresh("utils.task_sync", str(BACKEND_DIR / "utils" / "task_sync.py"))
        results = asyncio.run(task_sync.auto_sync_action_items_batch("user-456", items))

    assert len(results) == 2
    assert all(r["synced"] is False for r in results)
    assert all(r["error"] == "Auto-sync batch failed" for r in results)
    assert "INTERNAL_REDIS_AUTH_SECRET_LEAK" not in str(results)
