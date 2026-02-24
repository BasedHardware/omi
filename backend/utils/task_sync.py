from datetime import datetime
from typing import Optional

import database.users as users_db
import database.action_items as action_items_db
from utils.notifications import send_apple_reminders_sync_push
import logging

logger = logging.getLogger(__name__)


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
            return _sync_to_apple_reminders(uid, [action_item])
        else:
            return await _sync_to_cloud_service(uid, default_app, integration, action_item)

    except Exception as e:
        logger.info(f"Auto-sync failed for user {uid}: {e}")
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


def _sync_to_apple_reminders(uid: str, action_items: list) -> dict:
    """Send a single silent push with all action items for Apple Reminders."""
    success = send_apple_reminders_sync_push(user_id=uid, action_items=action_items)
    return {"synced": success, "platform": "apple_reminders", "pending_device": True}


async def auto_sync_action_items_batch(uid: str, action_items: list) -> list:
    """
    Batch sync multiple action items. For Apple Reminders, sends a single
    silent push with all items to avoid iOS throttling.

    Args:
        uid: User ID
        action_items: List of action item dicts, each containing at minimum 'id' and 'description'

    Returns:
        list: Results for each action item
    """
    if not action_items:
        return []

    try:
        default_app = users_db.get_default_task_integration(uid)
        if not default_app:
            return [{"synced": False, "reason": "no_default_integration"}] * len(action_items)

        integration = users_db.get_task_integration(uid, default_app)
        if not integration:
            return [{"synced": False, "reason": "integration_not_found"}] * len(action_items)

        if not integration.get("connected"):
            return [{"synced": False, "reason": "integration_not_connected"}] * len(action_items)

        # Apple Reminders: send all items in a single push
        if default_app == "apple_reminders":
            result = _sync_to_apple_reminders(uid, action_items)
            return [result] * len(action_items)

        # Cloud services: sync individually
        results = []
        for item in action_items:
            result = await _sync_to_cloud_service(uid, default_app, integration, item)
            results.append(result)
        return results

    except Exception as e:
        logger.info(f"Auto-sync batch failed for user {uid}: {e}")
        return [{"synced": False, "error": str(e)}] * len(action_items)
