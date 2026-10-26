"""
Tools for accessing Apple Health data synced from the user's iOS device.

Unlike Whoop which uses OAuth and live API calls, Apple Health data is synced
from the device to our backend and stored in Firestore.
"""

from datetime import date, datetime, time, timedelta, timezone
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


def _health_period_context(integration: Dict[str, Any], clock: DisplayClock, period_days: Any) -> str:
    """Describe the HealthKit window relative to its last successful sync."""
    try:
        days = int(period_days)
    except (TypeError, ValueError):
        days = 0

    synced_at = to_datetime(integration.get('last_synced'))
    start = synced_at - timedelta(days=days) if synced_at is not None and days > 0 else None
    lines = [f"Covered dates: {format_date(start, clock)} – {format_date(synced_at, clock)}."]
    lines.append(f"Data last synced: {format_instant(synced_at, clock)}.")
    if synced_at is not None and datetime.now(timezone.utc) - synced_at > timedelta(hours=24):
        lines.append("Data may be stale because the last sync was over 24 hours ago.")
    return "\n".join(lines)


def _workout_timestamp(workout: Dict[str, Any]) -> float:
    """Return a sortable epoch value for HealthKit's millisecond startDate."""
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
    if not integration:
        return None

    health_data: Dict[str, Any] = integration.get('health_data', {})

    if data_type:
        return health_data.get(data_type)

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
        health_data: Dict[str, Any] = integration.get('health_data', {})
        steps_data: Dict[str, Any] = health_data.get('steps', {})
        period_days = steps_data.get('period_days', health_data.get('period_days', 7))
        daily_steps: List[Dict[str, Any]] = steps_data.get('daily', [])
        context = _health_period_context(integration, clock, period_days)

        if not steps_data:
            return "No step data found. Make sure Apple Health is synced from your iPhone.\n" + context

        total_steps = steps_data.get('total', 0)
        avg_per_day = steps_data.get('average_per_day', 0)
        result = f"Apple Health Step Data\n{context}\n\n"
        result += f"Total Steps: {total_steps:,}\n"
        result += f"Average Steps per Day: {avg_per_day:,.0f}\n"

        # Include daily breakdown if available
        if daily_steps:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_steps, key=lambda x: x.get('date', ''), reverse=True)
            for day in sorted_days:
                date_str = _format_health_date(day.get('date'), clock)
                steps = day.get('steps', 0)
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
        health_data: Dict[str, Any] = integration.get('health_data', {})
        sleep_data: Dict[str, Any] = health_data.get('sleep', {})
        context = _health_period_context(integration, clock, health_data.get('period_days', 7))

        if not sleep_data:
            return "No sleep data found. Make sure Apple Health is synced from your iPhone.\n" + context

        total_sleep_hours = sleep_data.get('total_sleep_hours', 0)
        daily_sleep: List[Dict[str, Any]] = sleep_data.get('daily', [])

        result = f"Apple Health Sleep Data\n{context}\n\n"
        result += f"Total Sleep: {total_sleep_hours:.1f} hours\n"
        result += f"Average per Night: {total_sleep_hours / max(len(daily_sleep), 1):.1f} hours\n"

        # Include daily breakdown if available
        if daily_sleep:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_sleep, key=lambda x: x.get('date', ''), reverse=True)
            for day in sorted_days:
                date_str = _format_health_date(day.get('date'), clock)
                hours = day.get('sleepHours', 0)
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
        health_data: Dict[str, Any] = integration.get('health_data', {})
        heart_data: Dict[str, Any] = health_data.get('heart_rate', {})
        context = _health_period_context(integration, clock, health_data.get('period_days', 7))

        if not heart_data:
            return (
                "No heart rate data found. Make sure Apple Health is synced from your iPhone "
                "and you have heart rate data from Apple Watch.\n" + context
            )

        avg_hr = heart_data.get('average')
        min_hr = heart_data.get('minimum')
        max_hr = heart_data.get('maximum')

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
        health_data: Dict[str, Any] = integration.get('health_data', {})
        workouts: List[Dict[str, Any]] = health_data.get('workouts', [])
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
            duration = workout.get('durationMinutes', 0)
            calories = workout.get('caloriesBurned', 0)
            distance = workout.get('distanceKm')

            # Parse start date
            start_ms = workout.get('startDate', 0)
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
            if distance:
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
        health_data: Dict[str, Any] = integration.get('health_data', {})

        if not health_data:
            context = _health_period_context(integration, clock, 7)
            return "No health data found. Make sure Apple Health is synced from your iPhone.\n" + context

        period_days = health_data.get('period_days', 7)
        context = _health_period_context(integration, clock, period_days)
        result = f"Apple Health Summary\n{context}\n\n"

        # Steps with daily breakdown
        steps: Dict[str, Any] = health_data.get('steps', {})
        if steps:
            result += f"STEPS\n"
            result += f"  Total: {steps.get('total', 0):,}\n"
            result += f"  Daily Average: {steps.get('average_per_day', 0):,.0f}\n"
            daily_steps: List[Dict[str, Any]] = steps.get('daily', [])
            if daily_steps:
                result += "  Daily:\n"
                sorted_days = sorted(daily_steps, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {day.get('steps', 0):,}\n"
            result += "\n"

        # Active Energy with daily breakdown
        active_energy: Dict[str, Any] = health_data.get('active_energy', {})
        if active_energy:
            total_cal = active_energy.get('total', 0)
            avg_cal = active_energy.get('average_per_day', 0)
            result += f"ACTIVE ENERGY\n"
            result += f"  Total: {total_cal:,.0f} kcal\n"
            result += f"  Daily Average: {avg_cal:,.0f} kcal\n"
            daily_energy: List[Dict[str, Any]] = active_energy.get('daily', [])
            if daily_energy:
                result += "  Daily:\n"
                sorted_days = sorted(daily_energy, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {day.get('calories', 0):,.0f} kcal\n"
            result += "\n"

        # Sleep with daily breakdown
        sleep: Dict[str, Any] = health_data.get('sleep', {})
        if sleep:
            result += f"SLEEP\n"
            result += f"  Total Hours: {sleep.get('total_sleep_hours', 0):.1f}\n"
            daily_sleep: List[Dict[str, Any]] = sleep.get('daily', [])
            if daily_sleep:
                result += "  Daily:\n"
                sorted_days = sorted(daily_sleep, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {_format_health_date(day.get('date'), clock)}: {day.get('sleepHours', 0):.1f} hrs\n"
            result += "\n"

        # Heart Rate
        heart_rate: Dict[str, Any] = health_data.get('heart_rate', {})
        if heart_rate:
            result += f"HEART RATE\n"
            if heart_rate.get('average'):
                result += f"  Average: {heart_rate.get('average'):.0f} bpm\n"
            if heart_rate.get('minimum'):
                result += f"  Min: {heart_rate.get('minimum'):.0f} bpm\n"
            if heart_rate.get('maximum'):
                result += f"  Max: {heart_rate.get('maximum'):.0f} bpm\n"
            result += "\n"

        # Workouts
        workouts: List[Dict[str, Any]] = health_data.get('workouts', [])
        if workouts:
            result += f"WORKOUTS\n"
            result += f"  Total Workouts: {len(workouts)}\n"
            # Summarize workout types
            types: Dict[str, int] = {}
            for w in workouts:
                t = w.get('type', 'Unknown')
                types[t] = types.get(t, 0) + 1
            for t, count in types.items():
                result += f"  - {t}: {count}\n"

        return result.strip()

    except Exception as e:
        logger.error(f"Error in get_apple_health_summary_tool: {e}", exc_info=True)
        return "Failed to retrieve health summary."
