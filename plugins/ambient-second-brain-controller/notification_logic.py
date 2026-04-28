from typing import Any, Dict, Iterable, List

from models import ExtractedTask


def accountability_prompts(tasks: Iterable[ExtractedTask], rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prompts = []
    for task in tasks:
        if task.confidence < 0.6:
            continue
        for rule in rules:
            if not rule.get("enabled"):
                continue
            prompts.append(
                {
                    "rule_id": rule["id"],
                    "task_title": task.title,
                    "prompt": rule["prompt"].format(task=task.title),
                    "requires_confirmation": task.requires_confirmation,
                }
            )
    return prompts


def should_notify_for_health(event_type: str, health_state: str | None) -> bool:
    if event_type in {"policy_rejected", "permission_missing", "recovery_needed"}:
        return True
    return health_state in {"AUDIO_SILENCED_BY_SYSTEM", "STORAGE_LIMIT_REACHED", "SERVICE_KILLED"}
