from datetime import datetime, timezone


def parse_response_datetime(value, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return fallback
    return fallback


def response_float(value, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_goal_response(goal: dict) -> dict:
    normalized = dict(goal)
    now = datetime.now(timezone.utc)
    updated_at = parse_response_datetime(normalized.get('updated_at'), now)
    created_at = parse_response_datetime(normalized.get('created_at'), updated_at)
    normalized['id'] = str(normalized.get('id') or '')
    normalized['title'] = str(normalized.get('title') or '')
    normalized['goal_type'] = str(normalized.get('goal_type') or 'scale')
    normalized['target_value'] = response_float(normalized.get('target_value'), 0)
    normalized['current_value'] = response_float(normalized.get('current_value'), 0)
    normalized['min_value'] = response_float(normalized.get('min_value'), 0)
    normalized['max_value'] = response_float(normalized.get('max_value'), 10)
    normalized['is_active'] = bool(normalized.get('is_active', True))
    normalized['created_at'] = created_at
    normalized['updated_at'] = updated_at
    return normalized


def normalize_goal_history_entry(entry: dict) -> dict:
    normalized = dict(entry)
    normalized['date'] = str(normalized.get('date') or '')
    normalized['value'] = response_float(normalized.get('value'), 0)
    normalized['recorded_at'] = parse_response_datetime(normalized.get('recorded_at'), datetime.now(timezone.utc))
    return normalized
