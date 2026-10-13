from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

import database.users as users_db
import database.action_items as action_items_db
from utils.executors import db_executor, run_blocking
from utils.notifications import send_apple_reminders_sync_push_async
from utils.observability.fallback import record_fallback
from utils.task_integrations_ops import create_task_internal
import logging

logger = logging.getLogger(__name__)

# Closed outcomes for a single cloud create. The sweeper retries only the first two.
# ``in_doubt`` means the provider may already have the task (timeout after POST, or
# the create succeeded and the local ``exported`` write failed).
_PROVIDER_NOT_SENT = frozenset(
    {
        "no_access_token",
        "token_refresh_failed",
        "no_workspace",
        "no_list",
        "unsupported",
        "not_sent",
    }
)


def _provider_attempt_outcome(result: Dict[str, Any]) -> str:
    if result.get("success"):
        return "accepted"
    code = result.get("error_code")
    if code == "api_error":
        # A 5xx (or a gateway 504) can arrive after the provider committed the create.
        status = result.get("status_code")
        if isinstance(status, int) and status < 500:
            return "definite_error"
        return "in_doubt"
    if code in _PROVIDER_NOT_SENT:
        return "not_sent"
    return "in_doubt"


def _external_task_id(result: Dict[str, Any]) -> Any:
    external_id = result.get("external_task_id")
    if isinstance(external_id, str) and external_id:
        return external_id
    return None


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
            return {"synced": False, "reason": "no_default_integration", "provider_attempt_outcome": "not_sent"}

        integration = await run_blocking(db_executor, users_db.get_task_integration, uid, default_app)
        if not integration:
            return {"synced": False, "reason": "integration_not_found", "provider_attempt_outcome": "not_sent"}

        if not integration.get("connected"):
            return {"synced": False, "reason": "integration_not_connected", "provider_attempt_outcome": "not_sent"}

        # Route to appropriate handler
        if default_app == "apple_reminders":
            if skip_apple_reminders:
                return {"synced": False, "reason": "client_handles_sync", "provider_attempt_outcome": "not_sent"}
            result = await _sync_to_apple_reminders(uid, [action_item])
            result["provider_attempt_outcome"] = "not_sent"
            return result
        else:
            return await _sync_to_cloud_service(uid, default_app, integration, action_item)

    except Exception as e:
        logger.error(f"Auto-sync failed for user {uid}: {e}")
        return {"synced": False, "error": str(e), "provider_attempt_outcome": "not_sent"}


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
            return {
                "synced": True,
                "platform": app_key,
                "reason": "already_exported",
                "provider_attempt_outcome": "not_sent",
            }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            result = await create_task_internal(
                uid=uid,
                app_key=app_key,
                integration=integration,
                title=action_item["description"],
                due_date=action_item.get("due_at"),
                client=client,
            )
    except Exception:
        # Token refresh and other pre-POST failures raise out of create_task_internal.
        # Post-send timeouts are caught there and returned as error_code in_doubt.
        logger.error("Auto-sync create raised before a definite provider result user=%s app=%s", uid, app_key)
        return {
            "synced": False,
            "platform": app_key,
            "error": "integration_exception",
            "provider_attempt_outcome": "not_sent",
        }

    if result.get("success"):
        external_id = _external_task_id(result)
        exported = {
            "exported": True,
            "export_platform": app_key,
            "export_date": datetime.now(timezone.utc),
        }
        if external_id is not None:
            exported["external_task_id"] = external_id
        try:
            await run_blocking(
                db_executor,
                action_items_db.update_action_item,
                uid,
                action_item["id"],
                exported,
            )
        except Exception:
            logger.error("Auto-sync export marker write failed user=%s app=%s", uid, app_key)
            return {
                "synced": False,
                "platform": app_key,
                "error": "export_marker_failed",
                "provider_attempt_outcome": "in_doubt",
                "external_task_id": external_id,
            }
        return {
            "synced": True,
            "platform": app_key,
            "external_task_id": external_id,
            "provider_attempt_outcome": "accepted",
        }

    return {
        "synced": False,
        "platform": app_key,
        "error": result.get("error"),
        "provider_attempt_outcome": _provider_attempt_outcome(result),
    }


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

        # Cloud exports are independent. Preserve earlier outcomes and attempt the
        # tail even if a read, OAuth refresh, or export-marker write raises. Do not
        # retry here: the provider may have accepted a task before a local failure.
        results: List[Dict[str, Any]] = []
        for item in action_items:
            try:
                result = await _sync_to_cloud_service(uid, default_app, integration, item)
            except Exception as e:
                logger.error(
                    'Auto-sync item %s failed for user %s (%s): %s', item.get('id'), uid, default_app, type(e).__name__
                )
                record_fallback(
                    component='other',
                    from_mode='task_sync_batch',
                    to_mode='remaining_items',
                    reason='other',
                    outcome='degraded',
                )
                result = {'synced': False, 'platform': default_app, 'error': 'Auto-sync failed'}
            results.append(result)
        return results

    except Exception as e:
        logger.error(f"Auto-sync batch failed for user {uid}: {e}")
        return [{"synced": False, "error": str(e)}] * len(action_items)
