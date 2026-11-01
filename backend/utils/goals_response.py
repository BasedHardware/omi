from datetime import datetime, timezone

from pydantic import ValidationError

from utils.log_sanitizer import sanitize, sanitize_validation_error


def parse_response_datetime(value, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
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


def response_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'y', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'n', 'off'}:
            return False
        return fallback
    if isinstance(value, (int, float)):
        return value != 0
    return fallback


def response_int(value, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalize_goal_response(goal: dict) -> dict:
    normalized = dict(goal)
    now = datetime.now(timezone.utc)
    updated_at = parse_response_datetime(normalized.get('updated_at'), now)
    created_at = parse_response_datetime(normalized.get('created_at'), updated_at)
    normalized['id'] = str(normalized.get('id') or '')
    normalized['goal_id'] = str(normalized.get('goal_id') or normalized['id'])
    normalized['title'] = str(normalized.get('title') or '')
    normalized['desired_outcome'] = str(normalized.get('desired_outcome') or normalized['title'])
    normalized['why_it_matters'] = normalized.get('why_it_matters')
    success_criteria = normalized.get('success_criteria')
    if success_criteria is None:
        success_criteria = []
    elif not isinstance(success_criteria, list):
        raise ValueError('success_criteria must be a list')
    normalized['success_criteria'] = list(success_criteria)
    status = normalized.get('status')
    if status not in {'background', 'focused', 'paused', 'achieved', 'abandoned'}:
        status = 'background' if response_bool(normalized.get('is_active', True), True) else 'abandoned'
    normalized['status'] = status
    normalized['focus_rank'] = normalized.get('focus_rank') if status == 'focused' else None
    normalized['source'] = (
        normalized.get('source') if normalized.get('source') in {'user', 'ai_suggested', 'imported'} else 'imported'
    )
    metric = normalized.get('metric') if isinstance(normalized.get('metric'), dict) else None
    if metric is not None:
        normalized['goal_type'] = str(metric.get('type') or normalized.get('goal_type') or 'scale')
        normalized['target_value'] = response_float(metric.get('target'), 0)
        normalized['current_value'] = response_float(metric.get('current'), 0)
        normalized['min_value'] = response_float(metric.get('min'), 0)
        normalized['max_value'] = response_float(metric.get('max'), max(normalized['target_value'], 10))
        normalized['unit'] = metric.get('unit')
    else:
        normalized['metric'] = None
    normalized['goal_type'] = str(normalized.get('goal_type') or 'scale')
    normalized['target_value'] = response_float(normalized.get('target_value'), 0)
    normalized['current_value'] = response_float(normalized.get('current_value'), 0)
    normalized['min_value'] = response_float(normalized.get('min_value'), 0)
    normalized['max_value'] = response_float(normalized.get('max_value'), 10)
    normalized['is_active'] = status not in {'achieved', 'abandoned'}
    normalized['latest_progress_sequence'] = response_int(normalized.get('latest_progress_sequence'), 0)
    normalized['created_at'] = created_at
    normalized['updated_at'] = updated_at
    return normalized


def normalize_goal_history_entry(entry: dict) -> dict:
    normalized = dict(entry)
    normalized['date'] = str(normalized.get('date') or '')
    normalized['value'] = response_float(normalized.get('value'), 0)
    normalized['recorded_at'] = parse_response_datetime(normalized.get('recorded_at'), datetime.now(timezone.utc))
    return normalized


def list_developer_goals(
    uid: str, *, limit: int, include_inactive: bool, goals_db, response_model, logger
) -> list[dict]:
    """Fetch, normalize, and validate developer goal rows at the router boundary."""
    try:
        if include_inactive:
            # Pass the clamp down so the response honours the documented limit. The bound is
            # applied after the in-Python newest-first sort rather than at the query, because a
            # Firestore order_by('created_at') would silently exclude legacy goals that lack the
            # field; see get_all_goals.
            goals = goals_db.get_all_goals(uid, include_inactive=True, limit=limit)
        else:
            goals = goals_db.get_user_goals(uid, limit=limit)
    except Exception as exc:
        logger.error(
            'Developer goals list failed path=/v1/dev/user/goals uid=%s limit=%s include_inactive=%s error_type=%s',
            uid,
            limit,
            include_inactive,
            type(exc).__name__,
        )
        raise
    validated_goals = []
    for goal in goals:
        try:
            validated_goals.append(response_model.model_validate(normalize_goal_response(goal)).model_dump(mode='json'))
        except (AttributeError, TypeError, ValidationError, ValueError) as exc:
            goal_id = (goal.get('id') or goal.get('goal_id')) if isinstance(goal, dict) else 'unknown'
            details = sanitize_validation_error(exc) if isinstance(exc, ValidationError) else type(exc).__name__
            logger.warning(
                'Skipping malformed goal in Developer API goal list goal_id=%s errors=%s',
                sanitize(goal_id),
                details,
            )
    return validated_goals
