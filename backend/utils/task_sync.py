from datetime import datetime
from typing import Optional

import database.users as users_db
import database.action_items as action_items_db
from utils.notifications import send_apple_reminders_sync_push


async def auto_sync_action_item(uid: str, action_item: dict) -> dict:
    """
    Auto-sync a single action item to user's default integration.

    Args:
        uid: User ID
        action_item: Dict containing at minimum 'id' and 'description'

    Returns:
        dict: {"synced": bool, "platform": str, "external_task_id": str, "error": str}
    """
    try:
        default_app = users_db.get_default_task_integration(uid)
        if not default_app:
            return {"synced": False, "reason": "no_default_integration"}

        integration = users_db.get_task_integration(uid, default_app)
        if not integration:
            return {"synced": False, "reason": "integration_not_found"}

        if not integration.get("connected"):
            return {"synced": False, "reason": "integration_not_connected"}

        # Route to appropriate handler
        if default_app == "apple_reminders":
            return _sync_to_apple_reminders(uid, action_item)
        else:
            return await _sync_to_cloud_service(uid, default_app, integration, action_item)

    except Exception as e:
        print(f"Auto-sync failed for user {uid}: {e}")
        return {"synced": False, "error": str(e)}


async def _sync_to_cloud_service(uid: str, app_key: str, integration: dict, action_item: dict) -> dict:
    """Create task in external service using existing task_integrations logic."""
    from routers.task_integrations import _create_task_internal

    result = await _create_task_internal(
        uid=uid,
        app_key=app_key,
        integration=integration,
        title=action_item["description"],
        due_date=action_item.get("due_at"),
    )

    if result.get("success"):
        # Mark action item as exported
        action_items_db.update_action_item(
            uid,
            action_item["id"],
            {
                "exported": True,
                "export_platform": app_key,
                "export_date": datetime.utcnow(),
            },
        )
        return {"synced": True, "platform": app_key, "external_task_id": result.get("external_task_id")}

    return {"synced": False, "platform": app_key, "error": result.get("error")}


def _sync_to_apple_reminders(uid: str, action_item: dict) -> dict:
    """Send silent push to device for Apple Reminders."""
    success = send_apple_reminders_sync_push(
        user_id=uid,
        action_item_id=action_item["id"],
        description=action_item["description"],
        due_at=action_item.get("due_at"),
    )

    return {"synced": success, "platform": "apple_reminders", "pending_device": True}


async def auto_sync_action_items_batch(uid: str, action_items: list) -> list:
    """
    Batch sync multiple action items.

    Args:
        uid: User ID
        action_items: List of action item dicts, each containing at minimum 'id' and 'description'

    Returns:
        list: Results for each action item
    """
    results = []
    for item in action_items:
        result = await auto_sync_action_item(uid, item)
        results.append(result)
    return results
