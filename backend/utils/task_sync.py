from datetime import datetime
from typing import Optional

import httpx

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
        logger.error(f"Auto-sync failed for user {uid}: {e}")
        return {"synced": False, "error": str(e)}


async def _sync_to_cloud_service(uid: str, app_key: str, integration: dict, action_item: dict) -> dict:
    """Create task in external service using existing task_integrations logic."""
    from routers.task_integrations import _create_task_internal

    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await _create_task_internal(
            uid=uid,
            app_key=app_key,
            integration=integration,
            title=action_item["description"],
            due_date=action_item.get("due_at"),
            client=client,
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
        logger.error(f"Auto-sync batch failed for user {uid}: {e}")
        return [{"synced": False, "error": str(e)}] * len(action_items)




# *****************************
# ******* INBOUND SYNC ********
# (Fetch tasks FROM external services into Omi)
# *****************************


def _parse_external_date(date_str):
    """Parse date string from external service to datetime."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


async def _fetch_tasks_from_todoist(integration, client):
    """Fetch tasks from Todoist."""
    access_token = integration.get('access_token')
    if not access_token:
        return []

    try:
        response = await client.get(
            'https://api.todoist.com/rest/v2/tasks',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'filter': 'not completed'},
        )
        if response.status_code != 200:
            logger.warning(f"Todoist fetch failed: {response.status_code}")
            return []

        tasks = response.json()
        result = []
        for task in tasks:
            result.append({
                'external_task_id': str(task.get('id')),
                'platform': 'todoist',
                'title': task.get('content', ''),
                'description': task.get('description', '') or None,
                'due_date': _parse_external_date(task.get('due_date', {}).get('date')) if task.get('due_date') else None,
                'completed': task.get('is_completed', False),
                'external_created_at': _parse_external_date(task.get('created_at')),
                'external_updated_at': _parse_external_date(task.get('updated_at')),
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching Todoist tasks: {e}")
        return []


async def _fetch_tasks_from_asana(integration, client):
    """Fetch tasks from Asana."""
    access_token = integration.get('access_token')
    workspace_gid = integration.get('workspace_gid')
    if not access_token or not workspace_gid:
        return []

    try:
        response = await client.get(
            'https://app.asana.com/api/1.0/tasks',
            headers={'Authorization': f'Bearer {access_token}'},
            params={
                'workspace': workspace_gid,
                'completed': 'false',
                'opt_fields': 'name,notes,due_on,created_at,modified_at,completed',
            },
        )
        if response.status_code != 200:
            logger.warning(f"Asana fetch failed: {response.status_code}")
            return []

        tasks = response.json().get('data', [])
        result = []
        for task in tasks:
            result.append({
                'external_task_id': str(task.get('gid')),
                'platform': 'asana',
                'title': task.get('name', ''),
                'description': task.get('notes', '') or None,
                'due_date': _parse_external_date(task.get('due_on')),
                'completed': task.get('completed', False),
                'external_created_at': _parse_external_date(task.get('created_at')),
                'external_updated_at': _parse_external_date(task.get('modified_at')),
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching Asana tasks: {e}")
        return []


async def _fetch_tasks_from_google_tasks(integration, client):
    """Fetch tasks from Google Tasks."""
    access_token = integration.get('access_token')
    list_id = integration.get('default_list_id')
    if not access_token or not list_id:
        return []

    try:
        response = await client.get(
            f'https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'showCompleted': 'false'},
        )
        if response.status_code != 200:
            logger.warning(f"Google Tasks fetch failed: {response.status_code}")
            return []

        tasks = response.json().get('items', [])
        result = []
        for task in tasks:
            result.append({
                'external_task_id': str(task.get('id')),
                'platform': 'google_tasks',
                'title': task.get('title', ''),
                'description': task.get('notes', '') or None,
                'due_date': _parse_external_date(task.get('due')),
                'completed': task.get('status') == 'completed',
                'external_created_at': _parse_external_date(task.get('created')),
                'external_updated_at': _parse_external_date(task.get('updated')),
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching Google Tasks: {e}")
        return []


async def _fetch_tasks_from_clickup(integration, client):
    """Fetch tasks from ClickUp."""
    access_token = integration.get('access_token')
    list_id = integration.get('list_id')
    if not access_token or not list_id:
        return []

    try:
        response = await client.get(
            f'https://api.clickup.com/api/v2/list/{list_id}/task',
            headers={'Authorization': access_token},
            params={'subtasks': 'false', 'include_closed': 'false'},
        )
        if response.status_code != 200:
            logger.warning(f"ClickUp fetch failed: {response.status_code}")
            return []

        tasks = response.json().get('tasks', [])
        result = []
        for task in tasks:
            due_date_str = task.get('due_date')
            result.append({
                'external_task_id': str(task.get('id')),
                'platform': 'clickup',
                'title': task.get('name', ''),
                'description': task.get('description', '') or None,
                'due_date': _parse_external_date(due_date_str) if due_date_str else None,
                'completed': task.get('status', {}).get('status') == 'closed',
                'external_created_at': None,
                'external_updated_at': None,
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching ClickUp tasks: {e}")
        return []


async def _fetch_tasks_from_external_service(uid, app_key, integration, client):
    """Fetch all tasks from an external service."""
    if app_key == 'todoist':
        return await _fetch_tasks_from_todoist(integration, client)
    elif app_key == 'asana':
        return await _fetch_tasks_from_asana(integration, client)
    elif app_key == 'google_tasks':
        return await _fetch_tasks_from_google_tasks(integration, client)
    elif app_key == 'clickup':
        return await _fetch_tasks_from_clickup(integration, client)
    else:
        return []


def _get_action_items_with_external_ids(uid, platform):
    """Get mapping of external_task_id -> action_item_id for a given platform."""
    items = action_items_db.get_action_items(uid, completed=None, limit=500)
    mapping = {}
    for item in items:
        ext_id = item.get('external_task_id')
        if ext_id and item.get('export_platform') == platform:
            mapping[ext_id] = item['id']
    return mapping


def _sync_external_completion_status(uid, action_item_id, completed, platform, external_task_id):
    """Update Omi task completion status from external service."""
    try:
        item = action_items_db.get_action_item(uid, action_item_id)
        if not item:
            return
        # Only update completion for tasks that were synced FROM this platform
        synced_from = item.get('synced_from_platform')
        if not synced_from or synced_from != platform:
            return
        action_items_db.mark_action_item_completed(uid, action_item_id, completed)
        logger.info(f"Updated action_item {action_item_id} completion={completed} from {platform}")
    except Exception as e:
        logger.error(f"Error updating completion for {action_item_id}: {e}")


async def sync_tasks_from_external(uid, app_key=None):
    """
    Fetch tasks from external services and create/update action_items in Omi.
    This is the "pull" direction of two-way sync: external -> Omi.

    Args:
        uid: User ID
        app_key: Optional specific integration to sync. If None, syncs default integration.

    Returns:
        dict: {"synced": bool, "platform": str, "imported": int, "updated": int, "error": str}
    """
    try:
        if app_key:
            integration = users_db.get_task_integration(uid, app_key)
            if not integration:
                return {"synced": False, "error": f"Integration {app_key} not found"}
        else:
            app_key = users_db.get_default_task_integration(uid)
            if not app_key:
                return {"synced": False, "error": "No default integration configured"}
            integration = users_db.get_task_integration(uid, app_key)

        if not integration or not integration.get('connected'):
            return {"synced": False, "error": f"Integration {app_key} not connected"}

        if app_key == 'apple_reminders':
            return {"synced": False, "error": "Apple Reminders does not support server-side pull sync"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            external_tasks = await _fetch_tasks_from_external_service(uid, app_key, integration, client)

        if external_tasks is None:
            return {"synced": False, "error": f"Failed to fetch tasks from {app_key}"}

        existing_map = _get_action_items_with_external_ids(uid, app_key)

        imported = 0
        updated = 0

        for ext_task in external_tasks:
            ext_id = ext_task.get('external_task_id')
            if not ext_id:
                continue

            if ext_id in existing_map:
                action_item_id = existing_map[ext_id]
                item = action_items_db.get_action_item(uid, action_item_id)
                if item and item.get('completed') != ext_task.get('completed'):
                    _sync_external_completion_status(uid, action_item_id, ext_task.get('completed', False), app_key, ext_id)
                    updated += 1
            else:
                action_item_data = {
                    'description': ext_task.get('title', ''),
                    'completed': ext_task.get('completed', False),
                    'due_at': ext_task.get('due_date'),
                    'synced_from_platform': app_key,
                    'external_task_id': ext_id,
                    'exported': False,
                }
                new_id = action_items_db.create_action_item(uid, action_item_data)
                if new_id:
                    imported += 1
                    existing_map[ext_id] = new_id

        try:
            integration['last_inbound_sync'] = datetime.now(timezone.utc).isoformat()
            users_db.set_task_integration(uid, app_key, integration)
        except Exception as e:
            logger.warning(f"Failed to update last_inbound_sync: {e}")

        return {
            "synced": True,
            "platform": app_key,
            "imported": imported,
            "updated": updated,
            "total_external": len(external_tasks),
        }

    except Exception as e:
        logger.error(f"Inbound sync failed for user {uid}: {e}")
        return {"synced": False, "error": str(e)}
