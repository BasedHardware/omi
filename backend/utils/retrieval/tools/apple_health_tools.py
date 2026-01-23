"""
Tools for accessing Apple Health data synced from the user's iOS device.

Unlike Whoop which uses OAuth and live API calls, Apple Health data is synced
from the device to our backend and stored in Firestore.
"""

import contextvars
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import database.notifications as notification_db
from zoneinfo import ZoneInfo

from utils.retrieval.tools.integration_base import (
    resolve_config_uid,
    get_integration_checked,
)

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def get_apple_health_data(uid: str, data_type: str = None) -> Optional[dict]:
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

    health_data = integration.get('health_data', {})

    if data_type:
        return health_data.get(data_type)

    return health_data


def prepare_apple_health_access(
    config: Optional[dict],
) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    """
    Prepare access for Apple Health tools.

    Returns:
        Tuple of (uid, integration, error_or_none)
    """
    uid, uid_err = resolve_config_uid(config)
    if uid_err:
        return None, None, uid_err

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
    config: RunnableConfig = None,
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
    uid, integration, err = prepare_apple_health_access(config)
    if err:
        return err

    try:
        health_data = integration.get('health_data', {})
        steps_data = health_data.get('steps', {})

        if not steps_data:
            return "No step data found. Make sure Apple Health is synced from your iPhone."

        total_steps = steps_data.get('total', 0)
        avg_per_day = steps_data.get('average_per_day', 0)
        period_days = steps_data.get('period_days', 7)
        daily_steps = steps_data.get('daily', [])

        # Get last sync time
        last_synced = integration.get('last_synced')
        sync_info = ""
        if last_synced:
            try:
                sync_dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                sync_info = f"\n\n(Data last synced: {sync_dt.strftime('%Y-%m-%d %H:%M')} UTC)"
            except:
                pass

        result = f"Apple Health Step Data (Last {period_days} days):\n\n"
        result += f"Total Steps: {total_steps:,}\n"
        result += f"Average Steps per Day: {avg_per_day:,.0f}\n"

        # Include daily breakdown if available
        if daily_steps:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_steps, key=lambda x: x.get('date', ''), reverse=True)
            for day in sorted_days:
                date_str = day.get('date', 'Unknown')
                steps = day.get('steps', 0)
                result += f"  {date_str}: {steps:,} steps\n"

        result += sync_info

        return result.strip()

    except Exception as e:
        print(f"Error in get_apple_health_steps_tool: {e}")
        return f"Error retrieving step data: {str(e)}"


@tool
def get_apple_health_sleep_tool(
    config: RunnableConfig = None,
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
    uid, integration, err = prepare_apple_health_access(config)
    if err:
        return err

    try:
        health_data = integration.get('health_data', {})
        sleep_data = health_data.get('sleep', {})

        if not sleep_data:
            return "No sleep data found. Make sure Apple Health is synced from your iPhone."

        total_sleep_hours = sleep_data.get('total_sleep_hours', 0)
        total_in_bed_hours = sleep_data.get('total_in_bed_hours', 0)
        sessions_count = sleep_data.get('sessions_count', 0)
        daily_sleep = sleep_data.get('daily', [])

        result = f"Apple Health Sleep Data:\n\n"
        result += f"Total Sleep: {total_sleep_hours:.1f} hours\n"
        result += f"Average per Night: {total_sleep_hours / max(len(daily_sleep), 1):.1f} hours\n"

        # Include daily breakdown if available
        if daily_sleep:
            result += "\nDaily Breakdown:\n"
            # Sort by date descending (most recent first)
            sorted_days = sorted(daily_sleep, key=lambda x: x.get('date', ''), reverse=True)
            for day in sorted_days:
                date_str = day.get('date', 'Unknown')
                hours = day.get('sleepHours', 0)
                result += f"  {date_str}: {hours:.1f} hours\n"

        # Get last sync time
        last_synced = integration.get('last_synced')
        if last_synced:
            try:
                sync_dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                result += f"\n(Data last synced: {sync_dt.strftime('%Y-%m-%d %H:%M')} UTC)"
            except:
                pass

        return result.strip()

    except Exception as e:
        print(f"Error in get_apple_health_sleep_tool: {e}")
        return f"Error retrieving sleep data: {str(e)}"


@tool
def get_apple_health_heart_rate_tool(
    config: RunnableConfig = None,
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
    uid, integration, err = prepare_apple_health_access(config)
    if err:
        return err

    try:
        health_data = integration.get('health_data', {})
        heart_data = health_data.get('heart_rate', {})

        if not heart_data:
            return "No heart rate data found. Make sure Apple Health is synced from your iPhone and you have heart rate data from Apple Watch."

        avg_hr = heart_data.get('average')
        min_hr = heart_data.get('minimum')
        max_hr = heart_data.get('maximum')

        result = "Apple Health Heart Rate Data:\n\n"

        if avg_hr is not None:
            result += f"Average Heart Rate: {avg_hr:.0f} bpm\n"
        if min_hr is not None:
            result += f"Minimum Heart Rate: {min_hr:.0f} bpm\n"
        if max_hr is not None:
            result += f"Maximum Heart Rate: {max_hr:.0f} bpm\n"

        # Get last sync time
        last_synced = integration.get('last_synced')
        if last_synced:
            try:
                sync_dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                result += f"\n(Data last synced: {sync_dt.strftime('%Y-%m-%d %H:%M')} UTC)"
            except:
                pass

        return result.strip()

    except Exception as e:
        print(f"Error in get_apple_health_heart_rate_tool: {e}")
        return f"Error retrieving heart rate data: {str(e)}"


@tool
def get_apple_health_workouts_tool(
    config: RunnableConfig = None,
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
    uid, integration, err = prepare_apple_health_access(config)
    if err:
        return err

    try:
        health_data = integration.get('health_data', {})
        workouts = health_data.get('workouts', [])

        if not workouts:
            return "No workout data found. Make sure Apple Health is synced from your iPhone."

        # Get user timezone
        user_tz_str = notification_db.get_user_time_zone(uid)
        try:
            user_tz = ZoneInfo(user_tz_str)
        except Exception:
            user_tz = timezone.utc

        result = f"Apple Health Workouts ({len(workouts)} total):\n\n"

        for i, workout in enumerate(workouts[:10], 1):  # Show last 10 workouts
            workout_type = workout.get('type', 'Unknown')
            duration = workout.get('durationMinutes', 0)
            calories = workout.get('caloriesBurned', 0)
            distance = workout.get('distanceKm')

            # Parse start date
            start_ms = workout.get('startDate', 0)
            date_str = ""
            if start_ms:
                try:
                    start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).astimezone(user_tz)
                    date_str = f" - {start_dt.strftime('%m/%d %I:%M %p')}"
                except:
                    pass

            result += f"{i}. {workout_type}{date_str}\n"
            result += f"   Duration: {duration:.0f} minutes\n"
            if calories:
                result += f"   Calories: {calories:.0f} kcal\n"
            if distance:
                result += f"   Distance: {distance:.2f} km\n"
            result += "\n"

        # Get last sync time
        last_synced = integration.get('last_synced')
        if last_synced:
            try:
                sync_dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                result += f"(Data last synced: {sync_dt.strftime('%Y-%m-%d %H:%M')} UTC)"
            except:
                pass

        return result.strip()

    except Exception as e:
        print(f"Error in get_apple_health_workouts_tool: {e}")
        return f"Error retrieving workout data: {str(e)}"


@tool
def get_apple_health_summary_tool(
    config: RunnableConfig = None,
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
    uid, integration, err = prepare_apple_health_access(config)
    if err:
        return err

    try:
        health_data = integration.get('health_data', {})

        if not health_data:
            return "No health data found. Make sure Apple Health is synced from your iPhone."

        period_days = health_data.get('period_days', 7)
        result = f"Apple Health Summary (Last {period_days} days):\n\n"

        # Steps with daily breakdown
        steps = health_data.get('steps', {})
        if steps:
            result += f"STEPS\n"
            result += f"  Total: {steps.get('total', 0):,}\n"
            result += f"  Daily Average: {steps.get('average_per_day', 0):,.0f}\n"
            daily_steps = steps.get('daily', [])
            if daily_steps:
                result += "  Daily:\n"
                sorted_days = sorted(daily_steps, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {day.get('date', '?')}: {day.get('steps', 0):,}\n"
            result += "\n"

        # Active Energy with daily breakdown
        active_energy = health_data.get('active_energy', {})
        if active_energy:
            total_cal = active_energy.get('total', 0)
            avg_cal = active_energy.get('average_per_day', 0)
            result += f"ACTIVE ENERGY\n"
            result += f"  Total: {total_cal:,.0f} kcal\n"
            result += f"  Daily Average: {avg_cal:,.0f} kcal\n"
            daily_energy = active_energy.get('daily', [])
            if daily_energy:
                result += "  Daily:\n"
                sorted_days = sorted(daily_energy, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {day.get('date', '?')}: {day.get('calories', 0):,.0f} kcal\n"
            result += "\n"

        # Sleep with daily breakdown
        sleep = health_data.get('sleep', {})
        if sleep:
            result += f"SLEEP\n"
            result += f"  Total Hours: {sleep.get('total_sleep_hours', 0):.1f}\n"
            daily_sleep = sleep.get('daily', [])
            if daily_sleep:
                result += "  Daily:\n"
                sorted_days = sorted(daily_sleep, key=lambda x: x.get('date', ''), reverse=True)
                for day in sorted_days:
                    result += f"    {day.get('date', '?')}: {day.get('sleepHours', 0):.1f} hrs\n"
            result += "\n"

        # Heart Rate
        heart_rate = health_data.get('heart_rate', {})
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
        workouts = health_data.get('workouts', [])
        if workouts:
            result += f"WORKOUTS\n"
            result += f"  Total Workouts: {len(workouts)}\n"
            # Summarize workout types
            types = {}
            for w in workouts:
                t = w.get('type', 'Unknown')
                types[t] = types.get(t, 0) + 1
            for t, count in types.items():
                result += f"  - {t}: {count}\n"

        # Get last sync time
        last_synced = integration.get('last_synced')
        if last_synced:
            try:
                sync_dt = datetime.fromisoformat(last_synced.replace('Z', '+00:00'))
                result += f"\n(Data last synced: {sync_dt.strftime('%Y-%m-%d %H:%M')} UTC)"
            except:
                pass

        return result.strip()

    except Exception as e:
        print(f"Error in get_apple_health_summary_tool: {e}")
        return f"Error retrieving health summary: {str(e)}"
