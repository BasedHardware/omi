from typing import Any

from database.store import Filter, get_document_store


def _store():
    return get_document_store()


def create(task_data: dict[str, Any]) -> None:
    task_id = task_data['id']
    _store().set(f'tasks/{task_id}', task_data)


def update(task_id: str, task_data: dict[str, Any]) -> None:
    _store().update(f'tasks/{task_id}', task_data)


def get_task_by_action_request(action: str, request_id: str) -> dict[str, Any] | None:
    filters: list[Filter] = [('action', '==', action), ('request_id', '==', request_id)]
    docs = _store().query('tasks', filters=filters, limit=1)
    tasks: list[dict[str, Any]] = [item.to_dict() for item in docs]
    if len(tasks) > 0:
        return tasks[0]

    return None
