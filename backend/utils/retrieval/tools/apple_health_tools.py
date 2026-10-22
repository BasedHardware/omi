"""
Tools for accessing Apple Health data synced from the user's iOS device.

Unlike Whoop which uses OAuth and live API calls, Apple Health data is synced
from the device to our backend and stored in Firestore.
"""

from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

import database.users as users_db

from utils.retrieval.tools.integration_base import (
    resolve_config_uid,
    get_integration_checked,
)
from utils.model_text import DisplayClock, count_header, format_date, format_instant, to_datetime, truncation_note
from utils.user_clock import clock_for_config
import logging

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely coerce value to a finite float, rejecting booleans, non-numeric strings, NaNs, and Infs."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return default
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        try:
            val = float(s)
            if math.isnan(val) or math.isinf(val):
                return default
            return val
        except ValueError:
            return default
    return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Safely coerce value to an integer, rejecting booleans, non-integer floats, and non-numeric strings."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or not value.is_integer():
            return default
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
            try:
                return int(s)
            except ValueError:
                return default
        try:
            val = float(s)
            if not math.isnan(val) and not math.isinf(val) and val.is_integer():
                return int(val)
        except ValueError:
            pass
    return default


def _health_period_context(integration: Dict[str, Any], clock: DisplayClock, period_days: Any) -> str:
    """Describe the HealthKit window relative to its last successful sync."""
    try:
        days = int(period_days)
    except (TypeError, ValueError):
        days = 0

    synced_at = to_datetime(integration.get('last_synced') if isinstance(integration, dict) else None)
    start = synced_at - timedelta(days=days) if synced_at is not None and days > 0 else None
    lines = [f"Covered dates: {format_date(start, clock)} – {format_date(synced_at, clock)}."]
    lines.append(f"Data last synced: {format_instant(synced_at, clock)}.")
    if synced_at is not None and datetime.now(timezone.utc) - synced_at > timedelta(hours=24):
        lines.append("Data may be stale because the last sync was over 24 hours ago.")
    return "\n".join(lines)


def _workout_timestamp(workout: Any) -> float:
    """Return a sortable epoch value for HealthKit's millisecond startDate."""
    if not isinstance(workout, dict):
        return float('-inf')
    value = workout.get('startDate')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    parsed = to_datetime(value)
    return parsed.timestamp() * 1000 if parsed is not None else float('-inf')


def _format_health_date(value: Any, clock: DisplayClock) -> str:
    """Format HealthKit's local YYYY-MM-DD buckets without shifting their calendar day."""
    if isinstance(value, str):
        try:
            day = date.fromisoformat(value[:10])
            return format_date(datetime.combine(day, time.min).replace(tzinfo=clock.tz), clock)
        except ValueError:
            pass
    return format_date(value, clock)


def get_apple_health_data(uid: str, data_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve stored Apple Health data for a user.

    Args:
        uid: User ID
        data_type: Optional specific data type to retrieve ('steps', 'sleep', 'heart_rate', 'workouts', 'active_energy')

    Returns:
        Health data dict or None if not found
    """
    integration = users_db.get_integration(uid, 'apple_health')
    if not integration or not isinstance(integration, dict):
        return None

    health_data = integration.get('health_data')
    if not isinstance(health_data, dict):
        return None if data_type else {}

    if data_type:
        val = health_data.get(data_type)
        return val if isinstance(val, dict) else None

    return health_data


def prepare_apple_health_access(
    config: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Prepare access for Apple Health tools.

    Returns:
        Tuple of (uid, integration, error_or_none)
    """
    uid, uid_err = resolve_config_uid(config)
    if uid_err:
        return None, None, uid_err
    assert uid is not None

    integration, int_err = get_integration_checked(
        uid,
        'apple_health',
        'Apple Health',
        'Apple Health is not connected. Please connect Apple Health from settings on your iPhone to view your health data.',
        'Error checking Apple Health connection',
    )
    if int_err:
        return uid, None, int_err

    return uid, integration, None


@tool
def get_apple_health_steps_tool(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve step count data from the user's Apple Health.

    Use this tool when:
    - User asks about their steps, step count, or walking activity
    - User asks "how many steps did I take?" or "what's my step count?"
    - User asks about steps on a specific day like "yesterday" or "Monday"
    - User wants to know about their daily walking or activity level
    - User asks about their fitness or activity data from iPhone/Apple Watch
    - **ALWAYS use this tool when the user asks about step information from Apple Health**

    Returns:
        Formatted step count data with daily breakdown, averages and totals.
    """
    uid, integration, err = prepare_apple_health_access(cast(Optional[Dict[str, Any]], config))
    if err:
        return err
    assert uid is not None
    assert integration is not None
    clock = clock_for_config(config, uid)

    try:
        raw_health = integration.get('health_data')
        health_data: Dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        raw_steps = health_data.get('steps')
        steps_data: Dict[str, Any] = raw_steps if isinstance(raw_steps, dict) else {}
        period_days = steps_data.get('period_days', health_data.get('period_days', 7))
        raw_daily = steps_data.get('daily')
        daily_steps: List[Dict[str, Any]] = [d for d in raw_daily if isinstance(d, dict)] if isinstance(raw_daily, list) else []
        context = _health_period_context(integration, clock, period_days)

        if not steps_data:
            return "No step data found. Make sure Apple Health is synced from your iPhone.\n" + context

        total_steps = _safe_int(steps_data.get('total'), 0)
        avg_per_day = _safe_float(steps_data.get('average_per_day'), 0.0)
        result = f"Apple Health Step Data\n{context}\n\n"
        result += f"Total Steps: {total_steps:,}\n"
        result += f"Average Steps per Day: {avg_per_day:,.0f}\n"

        # Include daily breakdown if available
        if daily_steps:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_steps, key=lambda x: str(x.get('date') or ''), reverse=True)
            for day in sorted_days:
                date_str = _format_health_date(day.get('date'), clock)
                steps = _safe_int(day.get('steps'), 0)
                result += f"  {date_str}: {steps:,} steps\n"

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_steps_tool: {e}", exc_info=True)
        return "Failed to retrieve step data."


@tool
def get_apple_health_sleep_tool(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve sleep data from the user's Apple Health.

    Use this tool when:
    - User asks about their sleep from Apple Health or iPhone/Apple Watch
    - User asks "how did I sleep?" or "what's my sleep data?"
    - User asks about sleep on a specific day like "yesterday" or "last night"
    - User wants to know about their sleep duration, sleep quality, or sleep patterns
    - User asks about sleep stages (REM, deep sleep, core sleep)
    - **ALWAYS use this tool when the user asks about sleep information from Apple Health**

    Note: If the user has Whoop connected, they may want Whoop sleep data instead.
    Apple Health sleep data comes from iPhone or Apple Watch.

    Returns:
        Formatted sleep data with daily breakdown, total hours and session details.
    """
    uid, integration, err = prepare_apple_health_access(cast(Optional[Dict[str, Any]], config))
    if err:
        return err
    assert uid is not None
    assert integration is not None
    clock = clock_for_config(config, uid)

    try:
        raw_health = integration.get('health_data')
        health_data: Dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        raw_sleep = health_data.get('sleep')
        sleep_data: Dict[str, Any] = raw_sleep if isinstance(raw_sleep, dict) else {}
        context = _health_period_context(integration, clock, health_data.get('period_days', 7))

        if not sleep_data:
            return "No sleep data found. Make sure Apple Health is synced from your iPhone.\n" + context

        total_sleep_hours = _safe_float(sleep_data.get('total_sleep_hours'), 0.0)
        raw_daily = sleep_data.get('daily')
        daily_sleep: List[Dict[str, Any]] = [d for d in raw_daily if isinstance(d, dict)] if isinstance(raw_daily, list) else []

        avg_per_night = (total_sleep_hours / max(len(daily_sleep), 1)) if total_sleep_hours is not None else 0.0
        result = f"Apple Health Sleep Data\n{context}\n\n"
        result += f"Total Sleep: {total_sleep_hours:.1f} hours\n"
        result += f"Average per Night: {avg_per_night:.1f} hours\n"

        # Include daily breakdown if available
        if daily_sleep:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_sleep, key=lambda x: str(x.get('date') or ''), reverse=True)
            for day in sorted_days:
                date_str = _format_health_date(day.get('date'), clock)
                hours = _safe_float(day.get('sleepHours'), 0.0)
                result += f"  {date_str}: {hours:.1f} hours\n"

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_sleep_tool: {e}", exc_info=True)
        return "Failed to retrieve sleep data."


@tool
def get_apple_health_heart_rate_tool(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve heart rate data from the user's Apple Health.

    Use this tool when:
    - User asks about their heart rate from Apple Health or Apple Watch
    - User asks "what's my heart rate?" or "what's my resting heart rate?"
    - User wants to know about their average, minimum, or maximum heart rate
    - **ALWAYS use this tool when the user asks about heart rate from Apple Health**

    Note: If the user has Whoop connected, they may want Whoop heart rate data instead.
    Apple Health heart rate data typically comes from Apple Watch.

    Returns:
        Formatted heart rate data with average, min, and max values.
    """
    uid, integration, err = prepare_apple_health_access(cast(Optional[Dict[str, Any]], config))
    if err:
        return err
    assert uid is not None
    assert integration is not None
    clock = clock_for_config(config, uid)

    try:
        raw_health = integration.get('health_data')
        health_data: Dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        raw_heart = health_data.get('heart_rate')
        heart_data: Dict[str, Any] = raw_heart if isinstance(raw_heart, dict) else {}
        context = _health_period_context(integration, clock, health_data.get('period_days', 7))

        if not heart_data:
            return (
                "No heart rate data found. Make sure Apple Health is synced from your iPhone "
                "and you have heart rate data from Apple Watch.\n" + context
            )

        avg_hr = _safe_float(heart_data.get('average'))
        min_hr = _safe_float(heart_data.get('minimum'))
        max_hr = _safe_float(heart_data.get('maximum'))

        result = f"Apple Health Heart Rate Data\n{context}\n\n"

        if avg_hr is not None:
            result += f"Average Heart Rate: {avg_hr:.0f} bpm\n"
        if min_hr is not None:
            result += f"Minimum Heart Rate: {min_hr:.0f} bpm\n"
        if max_hr is not None:
            result += f"Maximum Heart Rate: {max_hr:.0f} bpm\n"

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_heart_rate_tool: {e}", exc_info=True)
        return "Failed to retrieve heart rate data."


@tool
def get_apple_health_workouts_tool(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve workout data from the user's Apple Health.

    Use this tool when:
    - User asks about their workouts or exercises from Apple Health
    - User asks "what workouts did I do?" or "show my exercises"
    - User wants to know about their workout history from iPhone/Apple Watch
    - User asks about calories burned, workout duration, or workout types
    - **ALWAYS use this tool when the user asks about workout information from Apple Health**

    Note: If the user has Whoop connected, they may want Whoop workout data instead.
    Apple Health workout data comes from Apple Watch or manually logged workouts.

    Returns:
        Formatted workout data with activity types, duration, and calories.
    """
    uid, integration, err = prepare_apple_health_access(cast(Optional[Dict[str, Any]], config))
    if err:
        return err
    assert uid is not None
    assert integration is not None
    clock = clock_for_config(config, uid)

    try:
        raw_health = integration.get('health_data')
        health_data: Dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        raw_workouts = health_data.get('workouts')
        workouts: List[Dict[str, Any]] = [w for w in raw_workouts if isinstance(w, dict)] if isinstance(raw_workouts, list) else []
        context = _health_period_context(integration, clock, health_data.get('period_days', 7))

        if not workouts:
            return "No workout data found. Make sure Apple Health is synced from your iPhone.\n" + context

        sorted_workouts = sorted(workouts, key=_workout_timestamp, reverse=True)
        shown_workouts = sorted_workouts[:10]
        result = count_header(
            "Apple Health Workouts",
            shown=len(shown_workouts),
            total=len(workouts),
            order="newest first",
        )
        result += f"\n{context}\n\n"

        for i, workout in enumerate(shown_workouts, 1):
            workout_type = workout.get('type', 'Unknown')
            duration = _safe_float(workout.get('durationMinutes'), 0.0)
            calories = _safe_float(workout.get('caloriesBurned'))
            distance = _safe_float(workout.get('distanceKm'))

            # Parse start date
            start_ms = _safe_float(workout.get('startDate'))
            date_str = ""
            if start_ms:
                try:
                    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
                    date_str = f" - {format_instant(start_dt, clock)}"
                except (ValueError, TypeError, OSError, OverflowError):
                    pass

            result += f"{i}. {workout_type}{date_str}\n"
            result += f"   Duration: {duration:.0f} minutes\n"
            if calories:
                result += f"   Calories: {calories:.0f} kcal\n"
            if distance is not None:
                result += f"   Distance: {distance:.2f} km\n"
            result += "\n"

        if len(workouts) > len(shown_workouts):
            result += (
                truncation_note(
                    shown=len(shown_workouts),
                    total=len(workouts),
                    unit="workouts",
                    how_to_get_more="Ask for a narrower workout period or a specific activity type.",
                )
                + "\n"
            )

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_workouts_tool: {e}", exc_info=True)
        return "Failed to retrieve workout data."


@tool
def get_apple_health_summary_tool(
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Retrieve a comprehensive health summary from the user's Apple Health.

    Use this tool when:
    - User asks for an overall health summary or health overview
    - User asks "how am I doing health-wise?" or "give me my health stats"
    - User wants a general picture of their health data from Apple Health
    - User asks about their overall fitness or wellness metrics
    - **ALWAYS use this tool when the user asks for a general health overview from Apple Health**

    This provides steps, sleep, heart rate, workouts, and active energy all in one response.

    Returns:
        Comprehensive health summary with all available Apple Health data.
    """
    uid, integration, err = prepare_apple_health_access(cast(Optional[Dict[str, Any]], config))
    if err:
        return err
    assert uid is not None
    assert integration is not None
    clock = clock_for_config(config, uid)

    try:
        raw_health = integration.get('health_data')
        health_data: Dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}

        if not health_data:
            context = _health_period_context(integration, clock, 7)
            return "No health data found. Make sure Apple Health is synced from your iPhone.\n" + context

        period_days = health_data.get('period_days', 7)
        context = _health_period_context(integration, clock, period_days)
        result = f"Apple Health Summary\n{context}\n\n"

        # Steps with daily breakdown
        raw_steps = health_data.get('steps')
        steps: Dict[str, Any] = raw_steps if isinstance(raw_steps, dict) else {}
        if steps:
            total_st = _safe_int(steps.get('total'), 0)
            avg_st = _safe_float(steps.get('average_per_day'), 0.0)
            result += f"STEPS\n"
            result += f"  Total: {total_st:,}\n"
            result += f"  Daily Average: {avg_st:,.0f}\n"
            raw_daily_steps = steps.get('daily')
            daily_steps: List[Dict[str, Any]] = [d for d in raw_daily_steps if isinstance(d, dict)] if isinstance(raw_daily_steps, list) else []
            if daily_steps:
                result += "  Daily:\n"
                sorted_days = sorted(daily_steps, key=lambda x: str(x.get('date') or ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {_safe_int(day.get('steps'), 0):,} steps\n"
            result += "\n"

        # Active Energy with daily breakdown
        raw_energy = health_data.get('active_energy')
        active_energy: Dict[str, Any] = raw_energy if isinstance(raw_energy, dict) else {}
        if active_energy:
            total_cal = _safe_float(active_energy.get('total'), 0.0)
            avg_cal = _safe_float(active_energy.get('average_per_day'), 0.0)
            result += f"ACTIVE ENERGY\n"
            result += f"  Total: {total_cal:,.0f} kcal\n"
            result += f"  Daily Average: {avg_cal:,.0f} kcal\n"
            raw_daily_energy = active_energy.get('daily')
            daily_energy: List[Dict[str, Any]] = [d for d in raw_daily_energy if isinstance(d, dict)] if isinstance(raw_daily_energy, list) else []
            if daily_energy:
                result += "  Daily:\n"
                sorted_days = sorted(daily_energy, key=lambda x: str(x.get('date') or ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {_safe_float(day.get('calories'), 0.0):,.0f} kcal\n"
            result += "\n"

        # Sleep with daily breakdown
        raw_sleep = health_data.get('sleep')
        sleep: Dict[str, Any] = raw_sleep if isinstance(raw_sleep, dict) else {}
        if sleep:
            result += f"SLEEP\n"
            result += f"  Total Hours: {_safe_float(sleep.get('total_sleep_hours'), 0.0):.1f}\n"
            raw_daily_sleep = sleep.get('daily')
            daily_sleep: List[Dict[str, Any]] = [d for d in raw_daily_sleep if isinstance(d, dict)] if isinstance(raw_daily_sleep, list) else []
            if daily_sleep:
                result += "  Daily:\n"
                sorted_days = sorted(daily_sleep, key=lambda x: str(x.get('date') or ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {_safe_float(day.get('sleepHours'), 0.0):.1f} hrs\n"
            result += "\n"

        # Heart Rate
        raw_heart = health_data.get('heart_rate')
        heart_rate: Dict[str, Any] = raw_heart if isinstance(raw_heart, dict) else {}
        if heart_rate:
            result += f"HEART RATE\n"
            avg_hr = _safe_float(heart_rate.get('average'))
            min_hr = _safe_float(heart_rate.get('minimum'))
            max_hr = _safe_float(heart_rate.get('maximum'))
            if avg_hr is not None:
                result += f"  Average: {avg_hr:.0f} bpm\n"
            if min_hr is not None:
                result += f"  Min: {min_hr:.0f} bpm\n"
            if max_hr is not None:
                result += f"  Max: {max_hr:.0f} bpm\n"
            result += "\n"

        # Workouts
        raw_workouts = health_data.get('workouts')
        workouts: List[Dict[str, Any]] = [w for w in raw_workouts if isinstance(w, dict)] if isinstance(raw_workouts, list) else []
        if workouts:
            result += f"WORKOUTS\n"
            result += f"  Total Workouts: {len(workouts)}\n"
            # Summarize workout types
            types: Dict[str, int] = {}
            for w in workouts:
                t = str(w.get('type') or 'Unknown')
                types[t] = types.get(t, 0) + 1
            for t, count in types.items():
                result += f"  - {t}: {count}\n"

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_summary_tool: {e}", exc_info=True)
        return "Failed to retrieve health summary."
