from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

import database.users as users_db
import database.action_items as action_items_db
from utils.executors import db_executor, run_blocking
from utils.notifications import send_apple_reminders_sync_push_async
from utils.task_integrations_ops import create_task_internal
import logging

logger = logging.getLogger(__name__)


async def auto_sync_action_item(
    uid: str, action_item: Dict[str, Any], skip_apple_reminders: bool = False
) -> Dict[str, Any]:
    """
    Auto-sync a single action item to user's default integration.

    Args:
        uid: User ID
        action_item: Dict containing at minimum 'id' and 'description'
        skip_apple_reminders: If True, skip Apple Reminders sync (app handles it directly)

    Returns:
        dict: {"synced": bool, "platform": str, "external_task_id": str, "error": str}
    """
    try:
        default_app = await run_blocking(db_executor, users_db.get_default_task_integration, uid)
        if not default_app:
            return {"synced": False, "reason": "no_default_integration"}

        integration = await run_blocking(db_executor, users_db.get_task_integration, uid, default_app)
        if not integration:
            return {"synced": False, "reason": "integration_not_found"}

        if not integration.get("connected"):
            return {"synced": False, "reason": "integration_not_connected"}

        # Route to appropriate handler
        if default_app == "apple_reminders":
            if skip_apple_reminders:
                return {"synced": False, "reason": "client_handles_sync"}
            return await _sync_to_apple_reminders(uid, [action_item])
        else:
            return await _sync_to_cloud_service(uid, default_app, integration, action_item)

    except Exception as e:
        logger.error(f"Auto-sync failed for user {uid}: {e}")
        return {"synced": False, "error": str(e)}


async def _sync_to_cloud_service(
    uid: str, app_key: str, integration: Dict[str, Any], action_item: Dict[str, Any]
) -> Dict[str, Any]:
    """Create task in external service using shared task integration ops."""
    # A retried POST /v1/action-items dedups the Firestore document by idempotency key but still
    # submits auto-sync, and create_task_internal has no idempotency key of its own. Re-read the
    # persisted export state and skip the external call when the item was already exported, so a
    # retry does not create a second task in the user's Todoist/Asana/ClickUp/Google Tasks.
    item_id = action_item.get("id")
    if item_id:
        existing = await run_blocking(db_executor, action_items_db.get_action_item, uid, item_id)
        if existing and existing.get("exported"):
            return {"synced": True, "platform": app_key, "reason": "already_exported"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await create_task_internal(
            uid=uid,
            app_key=app_key,
            integration=integration,
            title=action_item["description"],
            due_date=action_item.get("due_at"),
            client=client,
        )

    if result.get("success"):
        # Mark action item as exported
        await run_blocking(
            db_executor,
            action_items_db.update_action_item,
            uid,
            action_item["id"],
            {
                "exported": True,
                "export_platform": app_key,
                "export_date": datetime.now(timezone.utc),
            },
        )
        return {"synced": True, "platform": app_key, "external_task_id": result.get("external_task_id")}

    return {"synced": False, "platform": app_key, "error": result.get("error")}


async def _sync_to_apple_reminders(uid: str, action_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mark items as sync_requested and send a single silent push for Apple Reminders."""
    item_ids: List[Any] = [item['id'] for item in action_items]
    await run_blocking(db_executor, action_items_db.batch_set_sync_requested, uid, item_ids)
    success = await send_apple_reminders_sync_push_async(user_id=uid, action_items=action_items)
    return {"synced": success, "platform": "apple_reminders", "pending_device": True}


async def auto_sync_action_items_batch(uid: str, action_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        default_app = await run_blocking(db_executor, users_db.get_default_task_integration, uid)
        if not default_app:
            return [{"synced": False, "reason": "no_default_integration"}] * len(action_items)

        integration = await run_blocking(db_executor, users_db.get_task_integration, uid, default_app)
        if not integration:
            return [{"synced": False, "reason": "integration_not_found"}] * len(action_items)

        if not integration.get("connected"):
            return [{"synced": False, "reason": "integration_not_connected"}] * len(action_items)

        # Apple Reminders: send all items in a single push
        if default_app == "apple_reminders":
            result = await _sync_to_apple_reminders(uid, action_items)
            return [result] * len(action_items)

        # Cloud services: sync individually
        results: List[Dict[str, Any]] = []
        for item in action_items:
            result = await _sync_to_cloud_service(uid, default_app, integration, item)
            results.append(result)
        return results

    except Exception as e:
        logger.error(f"Auto-sync batch failed for user {uid}: {e}")
        return [{"synced": False, "error": str(e)}] * len(action_items)
