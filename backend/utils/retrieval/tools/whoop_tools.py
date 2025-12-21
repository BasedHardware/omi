"""
Tools for accessing Whoop health and fitness data.
"""

import os
import contextvars
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.users as users_db
import database.notifications as notification_db
import requests
from utils.retrieval.tools.integration_base import (
    ensure_capped,
    parse_iso_with_tz,
    prepare_access,
    retry_on_auth,
)

# Import the context variable from agentic module
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    # Fallback if import fails
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def refresh_whoop_token(uid: str, integration: Optional[dict] = None) -> Optional[str]:
    """
    Refresh Whoop access token using refresh token.

    Args:
        uid: User ID
        integration: Optional integration dict. If not provided, will reload from database.

    Returns:
        New access token or None if refresh failed
    """
    # Reload integration from database to ensure we have the latest refresh_token
    if integration is None:
        integration = users_db.get_integration(uid, 'whoop')

    if not integration:
        return None

    refresh_token = integration.get('refresh_token')
    if not refresh_token:
        return None

    client_id = os.getenv('WHOOP_CLIENT_ID')
    client_secret = os.getenv('WHOOP_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return None

    try:
        response = requests.post(
            'https://api.prod.whoop.com/oauth/oauth2/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
                'scope': 'offline',  # Required by Whoop API for refresh token requests
            },
            timeout=10.0,
        )

        if response.status_code == 200:
            token_data = response.json()
            new_access_token = token_data.get('access_token')

            if new_access_token:
                # Update stored token
                integration['access_token'] = new_access_token
                if 'refresh_token' in token_data:
                    integration['refresh_token'] = token_data.get('refresh_token')
                users_db.set_integration(uid, 'whoop', integration)
                return new_access_token
        else:
            error_body = response.text[:500] if response.text else "No error body"
            print(f"❌ Whoop token refresh failed with HTTP {response.status_code}: {error_body}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error refreshing Whoop token: {e}")
    except Exception as e:
        print(f"❌ Error refreshing Whoop token: {e}")

    return None


def get_whoop_sleep_data(
    access_token: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 10,
) -> dict:
    """
    Fetch sleep data from Whoop API.

    Args:
        access_token: Whoop access token
        start: Start datetime (defaults to 7 days ago)
        end: End datetime (defaults to now)
        limit: Maximum number of records to return (max 25)

    Returns:
        Dict with sleep records
    """
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(days=7)
    if end is None:
        end = datetime.now(timezone.utc)

    # Format times in ISO 8601 format
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'start': start_str,
        'end': end_str,
        'limit': min(limit, 25),  # Whoop API max is 25
    }

    try:
        all_records = []
        next_token = None
        while True:
            page_params = dict(params)
            if next_token:
                page_params['next_token'] = next_token

            response = requests.get(
                'https://api.prod.whoop.com/developer/v2/activity/sleep',
                headers={'Authorization': f'Bearer {access_token}'},
                params=page_params,
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                all_records.extend(data.get('records', []))
                if len(all_records) >= limit:
                    break
                next_token = data.get('next_token')
                if not next_token:
                    break
            elif response.status_code == 401:
                print(f"❌ Whoop Sleep API 401 - token expired")
                raise Exception("Authentication failed - token may be expired")
            else:
                error_body = response.text[:200] if response.text else "No error body"
                print(f"❌ Whoop Sleep API error {response.status_code}: {error_body}")
                raise Exception(f"Whoop Sleep API error: {response.status_code} - {error_body}")

        return {'records': all_records[:limit]}
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Whoop sleep data: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Whoop sleep data: {e}")
        raise


def get_whoop_recovery_data(
    access_token: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 10,
) -> dict:
    """
    Fetch recovery data from Whoop API.

    Args:
        access_token: Whoop access token
        start: Start datetime (defaults to 7 days ago)
        end: End datetime (defaults to now)
        limit: Maximum number of records to return (max 25)

    Returns:
        Dict with recovery records
    """
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(days=7)
    if end is None:
        end = datetime.now(timezone.utc)

    # Format times in ISO 8601 format
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'start': start_str,
        'end': end_str,
        'limit': min(limit, 25),  # Whoop API max is 25
    }

    try:
        all_records = []
        next_token = None
        while True:
            page_params = dict(params)
            if next_token:
                page_params['next_token'] = next_token

            response = requests.get(
                'https://api.prod.whoop.com/developer/v2/recovery',
                headers={'Authorization': f'Bearer {access_token}'},
                params=page_params,
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                all_records.extend(data.get('records', []))
                if len(all_records) >= limit:
                    break
                next_token = data.get('next_token')
                if not next_token:
                    break
            elif response.status_code == 401:
                print(f"❌ Whoop Recovery API 401 - token expired")
                raise Exception("Authentication failed - token may be expired")
            else:
                error_body = response.text[:200] if response.text else "No error body"
                print(f"❌ Whoop Recovery API error {response.status_code}: {error_body}")
                raise Exception(f"Whoop Recovery API error: {response.status_code} - {error_body}")

        return {'records': all_records[:limit]}
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Whoop recovery data: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Whoop recovery data: {e}")
        raise


def get_whoop_workout_data(
    access_token: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 10,
) -> dict:
    """
    Fetch workout data from Whoop API.

    Args:
        access_token: Whoop access token
        start: Start datetime (defaults to 7 days ago)
        end: End datetime (defaults to now)
        limit: Maximum number of records to return (max 25)

    Returns:
        Dict with workout records
    """
    if start is None:
        start = datetime.now(timezone.utc) - timedelta(days=7)
    if end is None:
        end = datetime.now(timezone.utc)

    # Format times in ISO 8601 format
    start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'start': start_str,
        'end': end_str,
        'limit': min(limit, 25),  # Whoop API max is 25
    }

    try:
        all_records = []
        next_token = None
        while True:
            page_params = dict(params)
            if next_token:
                page_params['next_token'] = next_token

            response = requests.get(
                'https://api.prod.whoop.com/developer/v2/activity/workout',
                headers={'Authorization': f'Bearer {access_token}'},
                params=page_params,
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                all_records.extend(data.get('records', []))
                if len(all_records) >= limit:
                    break
                next_token = data.get('next_token')
                if not next_token:
                    break
            elif response.status_code == 401:
                print(f"❌ Whoop Workout API 401 - token expired")
                raise Exception("Authentication failed - token may be expired")
            else:
                error_body = response.text[:200] if response.text else "No error body"
                print(f"❌ Whoop Workout API error {response.status_code}: {error_body}")
                raise Exception(f"Whoop Workout API error: {response.status_code} - {error_body}")

        return {'records': all_records[:limit]}
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching Whoop workout data: {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching Whoop workout data: {e}")
        raise


@tool
def get_whoop_sleep_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve sleep data from the user's Whoop account.

    Use this tool when:
    - User asks about their sleep, sleep quality, sleep duration, or sleep stages
    - User asks "how did I sleep?" or "what's my sleep data?"
    - User wants to know about REM sleep, deep sleep, or light sleep
    - User asks about sleep performance or sleep consistency
    - **ALWAYS use this tool when the user asks about sleep information**

    Date formatting and interpretation:
    - Dates should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T00:00:00-08:00" for January 20, 2024 at midnight in PST
    - If start_date is not provided, defaults to 7 days ago
    - If end_date is not provided, defaults to now

    **IMPORTANT: Relative date interpretation**
    - "last weekend" = the previous Saturday-Sunday (not the current weekend)
    - "this weekend" = the current/upcoming Saturday-Sunday
    - "yesterday" = the day before today
    - "last week" = 7 days ago to today
    - "last month" = the previous calendar month
    - Always calculate relative dates based on the CURRENT DATE AND TIME
    - If today is Saturday Nov 8, "last weekend" means Nov 1-2 (previous weekend)
    - If today is Saturday Nov 8, "this weekend" means Nov 8-9 (current weekend)
    - Weekend = Saturday 00:00:00 to Sunday 23:59:59 in user's timezone

    Args:
        start_date: Start date/time for sleep data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to 7 days ago if not provided.
        end_date: End date/time for sleep data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to now if not provided.
        limit: Maximum number of sleep records to return (default: 10, max: 25)

    Returns:
        Formatted list of sleep data with details like duration, sleep stages, performance, etc.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'whoop',
        'Whoop',
        'Whoop is not connected. Please connect your Whoop account from settings to view your sleep data.',
        'Whoop access token not found. Please reconnect your Whoop account from settings.',
        'Error checking Whoop connection',
    )
    if access_err:
        return access_err

    try:
        limit = ensure_capped(limit, 25, "⚠️ get_whoop_sleep_tool - limit capped from {} to {}")

        # Parse dates if provided
        time_start = None
        time_end = None

        time_start, err = parse_iso_with_tz(
            'start_date',
            start_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-20T00:00:00-08:00')",
        )
        if err:
            return err
        time_end, err = parse_iso_with_tz(
            'end_date',
            end_date,
            "in format YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., '2024-01-27T23:59:59-08:00')",
        )
        if err:
            return err

        # Fetch sleep data
        sleep_data, err = retry_on_auth(
            get_whoop_sleep_data,
            {
                'access_token': access_token,
                'start': time_start,
                'end': time_end,
                'limit': limit,
            },
            refresh_whoop_token,
            uid,
            users_db.get_integration(uid, 'whoop'),
            "Whoop authentication expired. Please reconnect your Whoop account from settings to restore access.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
            ),
        )
        if err:
            return err

        records = sleep_data.get('records', [])
        records_count = len(records) if records else 0

        if not records:
            date_info = ""
            if time_start and time_end:
                date_info = f" between {time_start.strftime('%Y-%m-%d')} and {time_end.strftime('%Y-%m-%d')}"
            elif time_start:
                date_info = f" after {time_start.strftime('%Y-%m-%d')}"
            elif time_end:
                date_info = f" before {time_end.strftime('%Y-%m-%d')}"

            return f"No sleep data found{date_info}."

        # Get user's timezone for display
        user_tz_str = notification_db.get_user_time_zone(uid)
        try:
            user_tz = ZoneInfo(user_tz_str)
        except Exception:
            # Fallback to UTC if timezone is invalid
            user_tz = timezone.utc
            user_tz_str = "UTC"

        # Format sleep records
        result = f"Sleep Data ({records_count} records):\n\n"

        for i, record in enumerate(records, 1):
            start_time = record.get('start', '')
            end_time = record.get('end', '')
            score = record.get('score', {})
            stage_summary = score.get('stage_summary', {})

            # Parse and format times (convert from UTC to user's timezone)
            try:
                # Parse UTC time from Whoop API
                start_dt_utc = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt_utc = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

                # Convert to user's timezone
                start_dt = start_dt_utc.astimezone(user_tz)
                end_dt = end_dt_utc.astimezone(user_tz)

                duration = end_dt_utc - start_dt_utc
                hours = duration.total_seconds() / 3600

                # Format with AM/PM
                start_time_str = start_dt.strftime('%I:%M %p').lstrip('0')
                end_time_str = end_dt.strftime('%I:%M %p').lstrip('0')
                date_str = start_dt.strftime('%Y-%m-%d')

                result += f"{i}. Sleep Session - {date_str} {start_time_str} to {end_time_str} ({hours:.1f} hours)\n"
            except Exception as e:
                print(f"❌ Error parsing sleep times: {e}")
                result += f"{i}. Sleep Session - {start_time} to {end_time}\n"

            # Sleep performance
            sleep_performance = score.get('sleep_performance_percentage')
            if sleep_performance is not None:
                result += f"   Performance: {sleep_performance}%\n"

            # Sleep stages
            if stage_summary:
                total_sleep_ms = (
                    stage_summary.get('total_light_sleep_time_milli', 0)
                    + stage_summary.get('total_slow_wave_sleep_time_milli', 0)
                    + stage_summary.get('total_rem_sleep_time_milli', 0)
                )
                total_sleep_hours = total_sleep_ms / 3600000

                rem_ms = stage_summary.get('total_rem_sleep_time_milli', 0)
                deep_ms = stage_summary.get('total_slow_wave_sleep_time_milli', 0)
                light_ms = stage_summary.get('total_light_sleep_time_milli', 0)

                result += f"   Total Sleep: {total_sleep_hours:.1f} hours\n"
                result += (
                    f"   - REM Sleep: {rem_ms / 3600000:.1f} hours ({rem_ms / total_sleep_ms * 100:.1f}%)\n"
                    if total_sleep_ms > 0
                    else ""
                )
                result += (
                    f"   - Deep Sleep: {deep_ms / 3600000:.1f} hours ({deep_ms / total_sleep_ms * 100:.1f}%)\n"
                    if total_sleep_ms > 0
                    else ""
                )
                result += (
                    f"   - Light Sleep: {light_ms / 3600000:.1f} hours ({light_ms / total_sleep_ms * 100:.1f}%)\n"
                    if total_sleep_ms > 0
                    else ""
                )

            # Sleep efficiency
            sleep_efficiency = score.get('sleep_efficiency_percentage')
            if sleep_efficiency is not None:
                result += f"   Sleep Efficiency: {sleep_efficiency:.1f}%\n"

            # Respiratory rate
            respiratory_rate = score.get('respiratory_rate')
            if respiratory_rate is not None:
                result += f"   Respiratory Rate: {respiratory_rate:.1f} breaths/min\n"

            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_whoop_sleep_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching sleep data: {str(e)}"


@tool
def get_whoop_recovery_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve recovery data from the user's Whoop account.

    Use this tool when:
    - User asks about their recovery, recovery score, or readiness
    - User asks "how recovered am I?" or "what's my recovery?"
    - User wants to know about heart rate variability (HRV) or resting heart rate
    - User asks about recovery metrics or recovery status
    - **ALWAYS use this tool when the user asks about recovery information**

    Date formatting and interpretation:
    - Dates should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T00:00:00-08:00" for January 20, 2024 at midnight in PST
    - If start_date is not provided, defaults to 7 days ago
    - If end_date is not provided, defaults to now

    **IMPORTANT: Relative date interpretation**
    - "last weekend" = the previous Saturday-Sunday (not the current weekend)
    - "this weekend" = the current/upcoming Saturday-Sunday
    - "yesterday" = the day before today
    - "last week" = 7 days ago to today
    - Always calculate relative dates based on the CURRENT DATE AND TIME

    Args:
        start_date: Start date/time for recovery data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to 7 days ago if not provided.
        end_date: End date/time for recovery data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to now if not provided.
        limit: Maximum number of recovery records to return (default: 10, max: 25)

    Returns:
        Formatted list of recovery data with details like recovery score, HRV, resting heart rate, etc.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'whoop',
        'Whoop',
        'Whoop is not connected. Please connect your Whoop account from settings to view your recovery data.',
        'Whoop access token not found. Please reconnect your Whoop account from settings.',
        'Error checking Whoop connection',
    )
    if access_err:
        return access_err

    try:
        limit = ensure_capped(limit, 25, "⚠️ get_whoop_recovery_tool - limit capped from {} to {}")

        # Parse dates if provided
        time_start = None
        time_end = None

        time_start, err = parse_iso_with_tz('start_date', start_date, "(with timezone)")
        if err:
            return err
        time_end, err = parse_iso_with_tz('end_date', end_date, "(with timezone)")
        if err:
            return err

        # Fetch recovery data
        recovery_data, err = retry_on_auth(
            get_whoop_recovery_data,
            {
                'access_token': access_token,
                'start': time_start,
                'end': time_end,
                'limit': limit,
            },
            refresh_whoop_token,
            uid,
            users_db.get_integration(uid, 'whoop'),
            "Whoop authentication expired. Please reconnect your Whoop account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
            ),
        )
        if err:
            return err

        records = recovery_data.get('records', [])
        if not records:
            return "No recovery data found for the specified time period."

        # Get user's timezone for display
        user_tz_str = notification_db.get_user_time_zone(uid)
        try:
            user_tz = ZoneInfo(user_tz_str)
        except Exception:
            # Fallback to UTC if timezone is invalid
            user_tz = timezone.utc
            user_tz_str = "UTC"

        # Format recovery records
        result = f"Recovery Data ({len(records)} records):\n\n"

        for i, record in enumerate(records, 1):
            score = record.get('score', {})
            recovery_score = score.get('recovery_score')
            hrv = score.get('hrv')
            resting_heart_rate = score.get('resting_heart_rate')

            # Parse date (convert from UTC to user's timezone)
            try:
                date_str = record.get('cycle_id', '') or record.get('created_at', '')
                if date_str:
                    date_dt_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    date_dt = date_dt_utc.astimezone(user_tz)
                    result += f"{i}. Recovery - {date_dt.strftime('%Y-%m-%d')}\n"
                else:
                    result += f"{i}. Recovery Record\n"
            except Exception as e:
                print(f"❌ Error parsing recovery date: {e}")
                result += f"{i}. Recovery Record\n"

            if recovery_score is not None:
                result += f"   Recovery Score: {recovery_score}%\n"
            if hrv is not None:
                result += f"   HRV: {hrv} ms\n"
            if resting_heart_rate is not None:
                result += f"   Resting Heart Rate: {resting_heart_rate} bpm\n"

            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_whoop_recovery_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching recovery data: {str(e)}"


@tool
def get_whoop_workout_tool(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> str:
    """
    Retrieve workout data from the user's Whoop account.

    Use this tool when:
    - User asks about their workouts, exercises, or activities
    - User asks "what workouts did I do?" or "show my activities"
    - User wants to know about strain, heart rate during workouts, or workout duration
    - User asks about specific sports or activities
    - **ALWAYS use this tool when the user asks about workout or activity information**

    Date formatting and interpretation:
    - Dates should be in ISO format with timezone: YYYY-MM-DDTHH:MM:SS+HH:MM
    - Example: "2024-01-20T00:00:00-08:00" for January 20, 2024 at midnight in PST
    - If start_date is not provided, defaults to 7 days ago
    - If end_date is not provided, defaults to now

    **IMPORTANT: Relative date interpretation**
    - "last weekend" = the previous Saturday-Sunday (not the current weekend)
    - "this weekend" = the current/upcoming Saturday-Sunday
    - "yesterday" = the day before today
    - "last week" = 7 days ago to today
    - Always calculate relative dates based on the CURRENT DATE AND TIME

    Args:
        start_date: Start date/time for workout data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to 7 days ago if not provided.
        end_date: End date/time for workout data in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). Defaults to now if not provided.
        limit: Maximum number of workout records to return (default: 10, max: 25)

    Returns:
        Formatted list of workout data with details like sport, strain, heart rate, duration, etc.
    """
    uid, integration, access_token, access_err = prepare_access(
        config,
        'whoop',
        'Whoop',
        'Whoop is not connected. Please connect your Whoop account from settings to view your workout data.',
        'Whoop access token not found. Please reconnect your Whoop account from settings.',
        'Error checking Whoop connection',
    )
    if access_err:
        return access_err

    try:
        limit = ensure_capped(limit, 25, "⚠️ get_whoop_workout_tool - limit capped from {} to {}")

        # Parse dates if provided
        time_start = None
        time_end = None

        time_start, err = parse_iso_with_tz('start_date', start_date, "(with timezone)")
        if err:
            return err
        time_end, err = parse_iso_with_tz('end_date', end_date, "(with timezone)")
        if err:
            return err

        # Fetch workout data
        workout_data, err = retry_on_auth(
            get_whoop_workout_data,
            {
                'access_token': access_token,
                'start': time_start,
                'end': time_end,
                'limit': limit,
            },
            refresh_whoop_token,
            uid,
            users_db.get_integration(uid, 'whoop'),
            "Whoop authentication expired. Please reconnect your Whoop account from settings.",
            (
                "Authentication failed",
                "401",
                "token may be expired",
            ),
        )
        if err:
            return err

        records = workout_data.get('records', [])
        if not records:
            return "No workout data found for the specified time period."

        # Get user's timezone for display
        user_tz_str = notification_db.get_user_time_zone(uid)
        try:
            user_tz = ZoneInfo(user_tz_str)
        except Exception:
            # Fallback to UTC if timezone is invalid
            user_tz = timezone.utc
            user_tz_str = "UTC"

        # Format workout records
        result = f"Workout Data ({len(records)} records):\n\n"

        for i, record in enumerate(records, 1):
            sport_name = record.get('sport_name', 'Unknown')
            score = record.get('score', {})
            strain = score.get('strain')
            avg_hr = score.get('average_heart_rate')
            max_hr = score.get('max_heart_rate')

            # Parse times (convert from UTC to user's timezone)
            try:
                start_time = record.get('start', '')
                end_time = record.get('end', '')
                if start_time:
                    start_dt_utc = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    start_dt = start_dt_utc.astimezone(user_tz)
                    time_str = start_dt.strftime('%I:%M %p').lstrip('0')
                    date_str = start_dt.strftime('%Y-%m-%d')
                    result += f"{i}. {sport_name.title()} - {date_str} {time_str}\n"
                else:
                    result += f"{i}. {sport_name.title()}\n"
            except Exception as e:
                print(f"❌ Error parsing workout times: {e}")
                result += f"{i}. {sport_name.title()}\n"

            if strain is not None:
                result += f"   Strain: {strain:.1f}\n"
            if avg_hr is not None:
                result += f"   Avg Heart Rate: {avg_hr} bpm\n"
            if max_hr is not None:
                result += f"   Max Heart Rate: {max_hr} bpm\n"

            # Duration
            try:
                if start_time and end_time:
                    start_dt_utc = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end_dt_utc = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    duration = end_dt_utc - start_dt_utc
                    minutes = duration.total_seconds() / 60
                    result += f"   Duration: {minutes:.0f} minutes\n"
            except:
                pass

            result += "\n"

        return result.strip()
    except Exception as e:
        print(f"❌ Unexpected error in get_whoop_workout_tool: {e}")
        import traceback

        traceback.print_exc()
        return f"Unexpected error fetching workout data: {str(e)}"
