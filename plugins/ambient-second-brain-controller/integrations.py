from typing import Any, Dict

import omi_client
import storage


def dispatch_task(omi_user_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
    destination = task.get("destination", "none")
    task_id = storage.store_task(omi_user_id, task)
    if destination == "omi":
        created = omi_client.create_omi_task(task)
        return {"stored_task_id": task_id, "destination": destination, "created": created is not None}
    return {"stored_task_id": task_id, "destination": destination, "created": False}


def integration_status(omi_user_id: str) -> Dict[str, Any]:
    settings = storage.get_settings(omi_user_id)
    return {"integrations": settings.integrations}
