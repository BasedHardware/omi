"""
Whoop Integration App for Omi

This app provides Whoop fitness tracker integration through OAuth2 authentication
and chat tools for accessing strain, recovery, sleep, and workout data.
"""
import os
import sys
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from db import (
    store_whoop_tokens,
    get_whoop_tokens,
    update_whoop_tokens,
    delete_whoop_tokens,
    store_oauth_state,
    get_uid_from_oauth_state,
    delete_oauth_state,
    store_user_setting,
    get_user_setting,
)
from models import ChatToolResponse

load_dotenv()


def log(msg: str):
    """Print and flush immediately for Railway logging."""
    print(msg)
    sys.stdout.flush()


# Whoop OAuth2 Configuration
WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
WHOOP_REDIRECT_URI = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8080/auth/whoop/callback")

# Whoop API endpoints
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"

# Scopes needed for Whoop access
WHOOP_SCOPES = [
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
    "offline"
]

app = FastAPI(
    title="Whoop Omi Integration",
    description="Whoop integration for Omi - Track your recovery, strain, and sleep with chat",
    version="1.0.0"
)


# ============================================
# Helper Functions
# ============================================

def get_valid_access_token(uid: str) -> Optional[str]:
    """
    Get a valid access token, refreshing if necessary.
    Returns None if user is not authenticated.
    """
    tokens = get_whoop_tokens(uid)
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at = tokens.get("expires_at")

    # Check if token is expired (with 5 minute buffer)
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(expiry.tzinfo) >= expiry - timedelta(minutes=5):
                # Token expired or about to expire, refresh it
                log(f"Token expired for {uid}, refreshing...")
                new_token = refresh_access_token(refresh_token)
                if new_token:
                    access_token = new_token["access_token"]
                    new_refresh = new_token.get("refresh_token", refresh_token)
                    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_token.get("expires_in", 3600))).isoformat() + "Z"
                    update_whoop_tokens(uid, access_token, new_refresh, new_expires_at)
                else:
                    return None
        except Exception as e:
            log(f"Error checking token expiry: {e}")

    return access_token


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh the access token using the refresh token."""
    try:
        response = requests.post(
            WHOOP_TOKEN_URL,
            data={
                "client_id": WHOOP_CLIENT_ID,
                "client_secret": WHOOP_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
        )

        if response.status_code == 200:
            return response.json()
        else:
            log(f"Token refresh failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        log(f"Error refreshing token: {e}")
        return None


def whoop_api_request(uid: str, method: str, endpoint: str, params: dict = None) -> Optional[dict]:
    """Make an authenticated request to the Whoop API."""
    access_token = get_valid_access_token(uid)
    if not access_token:
        return None

    url = f"{WHOOP_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        else:
            return None

        if response.status_code == 200:
            return response.json()
        else:
            log(f"Whoop API error: {response.status_code} - {response.text}")
            return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        log(f"Whoop API request error: {e}")
        return {"error": str(e)}


def format_recovery_score(recovery: dict) -> str:
    """Format recovery score for display."""
    score = recovery.get("score", {})
    recovery_score = score.get("recovery_score")
    hrv = score.get("hrv_rmssd_milli")
    rhr = score.get("resting_heart_rate")
    spo2 = score.get("spo2_percentage")
    skin_temp = score.get("skin_temp_celsius")

    if recovery_score is None:
        return "No recovery score available"

    # Determine recovery zone
    if recovery_score >= 67:
        zone = "Green (High)"
        emoji = "🟢"
    elif recovery_score >= 34:
        zone = "Yellow (Moderate)"
        emoji = "🟡"
    else:
        zone = "Red (Low)"
        emoji = "🔴"

    parts = [
        f"{emoji} **Recovery: {recovery_score}%** ({zone})",
        ""
    ]

    if hrv:
        parts.append(f"**HRV:** {hrv:.1f} ms")
    if rhr:
        parts.append(f"**Resting HR:** {rhr:.0f} bpm")
    if spo2:
        parts.append(f"**SpO2:** {spo2:.1f}%")
    if skin_temp:
        parts.append(f"**Skin Temp:** {skin_temp:.1f}°C")

    return "\n".join(parts)


def format_strain_score(cycle: dict) -> str:
    """Format strain score for display."""
    score = cycle.get("score", {})
    strain = score.get("strain")
    kilojoule = score.get("kilojoule")
    average_hr = score.get("average_heart_rate")
    max_hr = score.get("max_heart_rate")

    if strain is None:
        return "No strain data available"

    # Determine strain level
    if strain >= 18:
        level = "Very High (Overreaching)"
        emoji = "🔴"
    elif strain >= 14:
        level = "High"
        emoji = "🟠"
    elif strain >= 10:
        level = "Medium"
        emoji = "🟡"
    else:
        level = "Low"
        emoji = "🟢"

    parts = [
        f"{emoji} **Day Strain: {strain:.1f}** ({level})",
        ""
    ]

    if kilojoule:
        calories = kilojoule * 0.239006  # Convert kJ to kcal
        parts.append(f"**Calories Burned:** {calories:.0f} kcal")
    if average_hr:
        parts.append(f"**Average HR:** {average_hr:.0f} bpm")
    if max_hr:
        parts.append(f"**Max HR:** {max_hr:.0f} bpm")

    return "\n".join(parts)


def format_sleep(sleep: dict) -> str:
    """Format sleep data for display."""
    score = sleep.get("score", {})
    stage_summary = score.get("stage_summary", {})

    total_sleep = stage_summary.get("total_in_bed_time_milli", 0)
    total_awake = stage_summary.get("total_awake_time_milli", 0)
    total_light = stage_summary.get("total_light_sleep_time_milli", 0)
    total_slow = stage_summary.get("total_slow_wave_sleep_time_milli", 0)
    total_rem = stage_summary.get("total_rem_sleep_time_milli", 0)

    sleep_performance = score.get("sleep_performance_percentage")
    sleep_consistency = score.get("sleep_consistency_percentage")
    sleep_efficiency = score.get("sleep_efficiency_percentage")
    respiratory_rate = score.get("respiratory_rate")

    def ms_to_hours(ms):
        return ms / (1000 * 60 * 60) if ms else 0

    total_hours = ms_to_hours(total_sleep - total_awake)
    light_hours = ms_to_hours(total_light)
    deep_hours = ms_to_hours(total_slow)
    rem_hours = ms_to_hours(total_rem)

    parts = [f"**Total Sleep: {total_hours:.1f} hours**", ""]

    parts.append("**Sleep Stages:**")
    parts.append(f"  Light: {light_hours:.1f}h | Deep: {deep_hours:.1f}h | REM: {rem_hours:.1f}h")
    parts.append("")

    if sleep_performance:
        parts.append(f"**Sleep Performance:** {sleep_performance:.0f}%")
    if sleep_efficiency:
        parts.append(f"**Sleep Efficiency:** {sleep_efficiency:.0f}%")
    if sleep_consistency:
        parts.append(f"**Sleep Consistency:** {sleep_consistency:.0f}%")
    if respiratory_rate:
        parts.append(f"**Respiratory Rate:** {respiratory_rate:.1f} breaths/min")

    return "\n".join(parts)


def format_workout(workout: dict) -> str:
    """Format workout data for display."""
    sport_id = workout.get("sport_id", 0)
    score = workout.get("score", {})

    strain = score.get("strain")
    average_hr = score.get("average_heart_rate")
    max_hr = score.get("max_heart_rate")
    kilojoule = score.get("kilojoule")
    distance = score.get("distance_meter")
    zone_duration = score.get("zone_duration", {})

    start = workout.get("start")
    end = workout.get("end")

    # Sport names mapping (common ones)
    sport_names = {
        0: "Activity",
        1: "Running",
        16: "Cycling",
        32: "HIIT",
        33: "Strength Training",
        48: "Swimming",
        71: "Walking",
        82: "Yoga",
        -1: "Other"
    }
    sport_name = sport_names.get(sport_id, f"Activity {sport_id}")

    # Calculate duration
    duration_str = ""
    if start and end:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration = end_dt - start_dt
            minutes = int(duration.total_seconds() / 60)
            duration_str = f"{minutes} min"
        except:
            pass

    parts = [f"**{sport_name}**"]
    if duration_str:
        parts[0] += f" ({duration_str})"
    parts.append("")

    if strain:
        parts.append(f"**Strain:** {strain:.1f}")
    if kilojoule:
        calories = kilojoule * 0.239006
        parts.append(f"**Calories:** {calories:.0f} kcal")
    if distance:
        km = distance / 1000
        miles = km * 0.621371
        parts.append(f"**Distance:** {km:.2f} km ({miles:.2f} mi)")
    if average_hr:
        parts.append(f"**Avg HR:** {average_hr:.0f} bpm")
    if max_hr:
        parts.append(f"**Max HR:** {max_hr:.0f} bpm")

    return "\n".join(parts)


# ============================================
# Chat Tools Manifest
# ============================================

@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """
    Omi Chat Tools Manifest endpoint.
    """
    return {
        "tools": [
            {
                "name": "get_recovery",
                "description": "Get the user's recovery score and metrics from Whoop. Use this when the user asks about their recovery, readiness, HRV, or how recovered they are.",
                "endpoint": "/tools/get_recovery",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format. Defaults to today."
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your recovery data..."
            },
            {
                "name": "get_strain",
                "description": "Get the user's daily strain score from Whoop. Use this when the user asks about their strain, daily activity level, or how hard they've worked.",
                "endpoint": "/tools/get_strain",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format. Defaults to today."
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your strain data..."
            },
            {
                "name": "get_sleep",
                "description": "Get the user's sleep data from Whoop. Use this when the user asks about their sleep, sleep quality, sleep stages, or how they slept.",
                "endpoint": "/tools/get_sleep",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format. Gets sleep that ended on this date. Defaults to today."
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your sleep data..."
            },
            {
                "name": "get_workouts",
                "description": "Get the user's recent workouts from Whoop. Use this when the user asks about their workouts, exercises, or training sessions.",
                "endpoint": "/tools/get_workouts",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back (default: 7, max: 30)"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of workouts to return (default: 10)"
                        }
                    },
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your workouts..."
            },
            {
                "name": "get_weekly_summary",
                "description": "Get a summary of the user's week from Whoop including average recovery, strain, and sleep. Use this when the user wants a weekly overview or trends.",
                "endpoint": "/tools/get_weekly_summary",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your weekly summary..."
            },
            {
                "name": "get_body_measurements",
                "description": "Get the user's body measurements from Whoop including height, weight, and max heart rate.",
                "endpoint": "/tools/get_body_measurements",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your body measurements..."
            },
            {
                "name": "get_profile",
                "description": "Get the user's Whoop profile information.",
                "endpoint": "/tools/get_profile",
                "method": "POST",
                "parameters": {
                    "properties": {},
                    "required": []
                },
                "auth_required": True,
                "status_message": "Getting your profile..."
            }
        ]
    }


# ============================================
# Chat Tool Endpoints
# ============================================

@app.post("/tools/get_recovery", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_recovery(request: Request):
    """Get recovery score and metrics."""
    try:
        body = await request.json()
        log(f"=== GET_RECOVERY ===")

        uid = body.get("uid")
        date_str = body.get("date")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        # Build date filter
        params = {"limit": 1}
        if date_str:
            # Filter for specific date
            params["start"] = f"{date_str}T00:00:00.000Z"
            params["end"] = f"{date_str}T23:59:59.999Z"

        result = whoop_api_request(uid, "GET", "/recovery", params=params)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get recovery: {result.get('error', 'Unknown error')}")

        records = result.get("records", [])

        if not records:
            return ChatToolResponse(result="No recovery data available for this date.")

        recovery = records[0]
        cycle_id = recovery.get("cycle_id")
        created_at = recovery.get("created_at", "")[:10]

        result_parts = [
            f"**Recovery for {created_at}**",
            "",
            format_recovery_score(recovery)
        ]

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting recovery: {e}")
        import traceback
        traceback.print_exc()
        return ChatToolResponse(error=f"Failed to get recovery: {str(e)}")


@app.post("/tools/get_strain", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_strain(request: Request):
    """Get daily strain score."""
    try:
        body = await request.json()
        log(f"=== GET_STRAIN ===")

        uid = body.get("uid")
        date_str = body.get("date")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        # Build date filter
        params = {"limit": 1}
        if date_str:
            params["start"] = f"{date_str}T00:00:00.000Z"
            params["end"] = f"{date_str}T23:59:59.999Z"

        result = whoop_api_request(uid, "GET", "/cycle", params=params)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get strain: {result.get('error', 'Unknown error')}")

        records = result.get("records", [])

        if not records:
            return ChatToolResponse(result="No strain data available for this date.")

        cycle = records[0]
        start_date = cycle.get("start", "")[:10]

        result_parts = [
            f"**Strain for {start_date}**",
            "",
            format_strain_score(cycle)
        ]

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting strain: {e}")
        return ChatToolResponse(error=f"Failed to get strain: {str(e)}")


@app.post("/tools/get_sleep", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_sleep(request: Request):
    """Get sleep data."""
    try:
        body = await request.json()
        log(f"=== GET_SLEEP ===")

        uid = body.get("uid")
        date_str = body.get("date")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        # Build date filter
        params = {"limit": 1}
        if date_str:
            params["start"] = f"{date_str}T00:00:00.000Z"
            params["end"] = f"{date_str}T23:59:59.999Z"

        result = whoop_api_request(uid, "GET", "/activity/sleep", params=params)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get sleep: {result.get('error', 'Unknown error')}")

        records = result.get("records", [])

        if not records:
            return ChatToolResponse(result="No sleep data available for this date.")

        sleep = records[0]
        end_date = sleep.get("end", "")[:10]

        result_parts = [
            f"**Sleep ending {end_date}**",
            "",
            format_sleep(sleep)
        ]

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting sleep: {e}")
        return ChatToolResponse(error=f"Failed to get sleep: {str(e)}")


@app.post("/tools/get_workouts", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_workouts(request: Request):
    """Get recent workouts."""
    try:
        body = await request.json()
        log(f"=== GET_WORKOUTS ===")

        uid = body.get("uid")
        days = min(body.get("days", 7), 30)
        max_results = min(body.get("max_results", 10), 50)

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        params = {
            "start": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "end": end_date.strftime("%Y-%m-%dT23:59:59.999Z"),
            "limit": max_results
        }

        result = whoop_api_request(uid, "GET", "/activity/workout", params=params)

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get workouts: {result.get('error', 'Unknown error')}")

        workouts = result.get("records", [])

        if not workouts:
            return ChatToolResponse(result=f"No workouts in the last {days} days.")

        result_parts = [f"**Workouts (Last {days} Days)**", ""]

        for workout in workouts:
            result_parts.append(format_workout(workout))
            result_parts.append("")
            result_parts.append("---")
            result_parts.append("")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting workouts: {e}")
        return ChatToolResponse(error=f"Failed to get workouts: {str(e)}")


@app.post("/tools/get_weekly_summary", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_weekly_summary(request: Request):
    """Get weekly summary of recovery, strain, and sleep."""
    try:
        body = await request.json()
        log(f"=== GET_WEEKLY_SUMMARY ===")

        uid = body.get("uid")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        # Get last 7 days of data
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)

        params = {
            "start": start_date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "end": end_date.strftime("%Y-%m-%dT23:59:59.999Z"),
            "limit": 7
        }

        # Fetch recovery, cycles, and sleep
        recovery_result = whoop_api_request(uid, "GET", "/recovery", params=params)
        cycle_result = whoop_api_request(uid, "GET", "/cycle", params=params)
        sleep_result = whoop_api_request(uid, "GET", "/activity/sleep", params=params)

        # Calculate averages
        recovery_scores = []
        if recovery_result and "records" in recovery_result:
            for r in recovery_result["records"]:
                score = r.get("score", {}).get("recovery_score")
                if score is not None:
                    recovery_scores.append(score)

        strain_scores = []
        if cycle_result and "records" in cycle_result:
            for c in cycle_result["records"]:
                strain = c.get("score", {}).get("strain")
                if strain is not None:
                    strain_scores.append(strain)

        sleep_hours = []
        if sleep_result and "records" in sleep_result:
            for s in sleep_result["records"]:
                summary = s.get("score", {}).get("stage_summary", {})
                total = summary.get("total_in_bed_time_milli", 0)
                awake = summary.get("total_awake_time_milli", 0)
                sleep_ms = total - awake
                if sleep_ms > 0:
                    sleep_hours.append(sleep_ms / (1000 * 60 * 60))

        result_parts = ["**Weekly Summary (Last 7 Days)**", ""]

        if recovery_scores:
            avg_recovery = sum(recovery_scores) / len(recovery_scores)
            min_recovery = min(recovery_scores)
            max_recovery = max(recovery_scores)
            result_parts.append(f"**Recovery:** Avg {avg_recovery:.0f}% (Range: {min_recovery:.0f}%-{max_recovery:.0f}%)")
        else:
            result_parts.append("**Recovery:** No data")

        if strain_scores:
            avg_strain = sum(strain_scores) / len(strain_scores)
            total_strain = sum(strain_scores)
            result_parts.append(f"**Strain:** Avg {avg_strain:.1f} (Total: {total_strain:.1f})")
        else:
            result_parts.append("**Strain:** No data")

        if sleep_hours:
            avg_sleep = sum(sleep_hours) / len(sleep_hours)
            min_sleep = min(sleep_hours)
            max_sleep = max(sleep_hours)
            result_parts.append(f"**Sleep:** Avg {avg_sleep:.1f}h (Range: {min_sleep:.1f}h-{max_sleep:.1f}h)")
        else:
            result_parts.append("**Sleep:** No data")

        # Add workout count
        workout_result = whoop_api_request(uid, "GET", "/activity/workout", params=params)
        workout_count = len(workout_result.get("records", [])) if workout_result else 0
        result_parts.append(f"**Workouts:** {workout_count}")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting weekly summary: {e}")
        return ChatToolResponse(error=f"Failed to get weekly summary: {str(e)}")


@app.post("/tools/get_body_measurements", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_body_measurements(request: Request):
    """Get body measurements."""
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        result = whoop_api_request(uid, "GET", "/body_measurement")

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get measurements: {result.get('error', 'Unknown error')}")

        height_m = result.get("height_meter")
        weight_kg = result.get("weight_kilogram")
        max_hr = result.get("max_heart_rate")

        result_parts = ["**Body Measurements**", ""]

        if height_m:
            height_cm = height_m * 100
            height_ft = height_m * 3.28084
            feet = int(height_ft)
            inches = (height_ft - feet) * 12
            result_parts.append(f"**Height:** {height_cm:.0f} cm ({feet}'{inches:.0f}\")")

        if weight_kg:
            weight_lb = weight_kg * 2.20462
            result_parts.append(f"**Weight:** {weight_kg:.1f} kg ({weight_lb:.1f} lb)")

        if max_hr:
            result_parts.append(f"**Max Heart Rate:** {max_hr:.0f} bpm")

        if len(result_parts) == 2:
            return ChatToolResponse(result="No body measurements available.")

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting body measurements: {e}")
        return ChatToolResponse(error=f"Failed to get measurements: {str(e)}")


@app.post("/tools/get_profile", tags=["chat_tools"], response_model=ChatToolResponse)
async def tool_get_profile(request: Request):
    """Get Whoop profile."""
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return ChatToolResponse(error="User ID is required")

        access_token = get_valid_access_token(uid)
        if not access_token:
            return ChatToolResponse(error="Please connect your Whoop first in the app settings.")

        result = whoop_api_request(uid, "GET", "/user/profile/basic")

        if not result or "error" in result:
            return ChatToolResponse(error=f"Failed to get profile: {result.get('error', 'Unknown error')}")

        first_name = result.get("first_name", "")
        last_name = result.get("last_name", "")
        email = result.get("email", "")
        user_id = result.get("user_id", "")

        result_parts = [
            "**Whoop Profile**",
            "",
            f"**Name:** {first_name} {last_name}",
            f"**Email:** {email}",
            f"**User ID:** {user_id}"
        ]

        return ChatToolResponse(result="\n".join(result_parts))

    except Exception as e:
        log(f"Error getting profile: {e}")
        return ChatToolResponse(error=f"Failed to get profile: {str(e)}")


# ============================================
# OAuth & Setup Endpoints
# ============================================

@app.get("/")
async def root(uid: str = Query(None)):
    """Root endpoint - Homepage."""
    if not uid:
        return {
            "app": "Whoop Omi Integration",
            "version": "1.0.0",
            "status": "active",
            "endpoints": {
                "auth": "/auth/whoop?uid=<user_id>",
                "setup_check": "/setup/whoop?uid=<user_id>",
                "tools_manifest": "/.well-known/omi-tools.json"
            }
        }

    tokens = get_whoop_tokens(uid)

    if not tokens:
        auth_url = f"/auth/whoop?uid={uid}"
        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Whoop - Connect</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="icon">💪</div>
                    <h1>Whoop</h1>
                    <p>Track your recovery, strain, and sleep through Omi chat</p>

                    <a href="{auth_url}" class="btn btn-primary btn-block">
                        Connect Whoop
                    </a>

                    <div class="card">
                        <h3>What You Can Do</h3>
                        <ul>
                            <li><strong>Recovery</strong> - Check your recovery score and HRV</li>
                            <li><strong>Strain</strong> - See your daily strain level</li>
                            <li><strong>Sleep</strong> - View sleep duration and quality</li>
                            <li><strong>Workouts</strong> - Track your training sessions</li>
                        </ul>
                    </div>

                    <div class="card">
                        <h3>Example Commands</h3>
                        <div class="example">"What's my recovery today?"</div>
                        <div class="example">"How did I sleep last night?"</div>
                        <div class="example">"Show my weekly summary"</div>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    # User is connected
    return HTMLResponse(content=f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Whoop - Connected</title>
            <style>{get_css()}</style>
        </head>
        <body>
            <div class="container">
                <div class="success-box">
                    <div class="icon" style="font-size: 48px;">✓</div>
                    <h2>Whoop Connected</h2>
                    <p>Your Whoop is linked to Omi</p>
                </div>

                <div class="card">
                    <h3>Try These Commands</h3>
                    <div class="example">"What's my recovery score?"</div>
                    <div class="example">"How much strain do I have today?"</div>
                    <div class="example">"Show my recent workouts"</div>
                </div>

                <a href="/disconnect?uid={uid}" class="btn btn-secondary btn-block">
                    Disconnect Whoop
                </a>

                <div class="footer">Powered by <strong>Omi</strong></div>
            </div>
        </body>
    </html>
    """)


@app.get("/auth/whoop")
async def whoop_auth(uid: str = Query(...)):
    """Start Whoop OAuth2 flow."""
    if not WHOOP_CLIENT_ID or not WHOOP_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Whoop OAuth credentials not configured")

    # Whoop requires state to be at least 8 characters
    state = secrets.token_urlsafe(16)
    store_oauth_state(state, uid)

    params = {
        "client_id": WHOOP_CLIENT_ID,
        "redirect_uri": WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(WHOOP_SCOPES),
        "state": state
    }

    auth_url = f"{WHOOP_AUTH_URL}?{urlencode(params)}"
    log(f"=== WHOOP AUTH ===")
    log(f"Client ID: {WHOOP_CLIENT_ID[:8]}...")
    log(f"Redirect URI: {WHOOP_REDIRECT_URI}")
    log(f"Scopes: {' '.join(WHOOP_SCOPES)}")
    log(f"State: {state}")
    log(f"Auth URL: {auth_url}")
    return RedirectResponse(url=auth_url)


@app.get("/auth/whoop/callback")
async def whoop_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None)
):
    """Handle Whoop OAuth2 callback."""
    if error:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>{error}</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    if not code or not state:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Authorization Failed</h2>
                        <p>Missing authorization code or state.</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    # Look up uid from state (Whoop requires 8-char state, so we store state->uid mapping)
    uid = get_uid_from_oauth_state(state)
    if not uid:
        return HTMLResponse(content=f"""
        <html>
            <head><style>{get_css()}</style></head>
            <body>
                <div class="container">
                    <div class="error-box">
                        <h2>Session Expired</h2>
                        <p>Please try connecting again.</p>
                    </div>
                </div>
            </body>
        </html>
        """, status_code=400)

    delete_oauth_state(state)

    # Exchange code for tokens
    try:
        response = requests.post(
            WHOOP_TOKEN_URL,
            data={
                "client_id": WHOOP_CLIENT_ID,
                "client_secret": WHOOP_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": WHOOP_REDIRECT_URI
            }
        )

        if response.status_code != 200:
            log(f"Token exchange failed: {response.text}")
            return HTMLResponse(content=f"Token exchange failed: {response.text}", status_code=400)

        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)

        if not access_token:
            return HTMLResponse(content="No access token received", status_code=400)

        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

        store_whoop_tokens(uid, access_token, refresh_token, expires_at)

        return HTMLResponse(content=f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Connected!</title>
                <style>{get_css()}</style>
            </head>
            <body>
                <div class="container">
                    <div class="success-box">
                        <div class="icon" style="font-size: 72px;">🎉</div>
                        <h2>Successfully Connected!</h2>
                        <p>Your Whoop is now linked to Omi</p>
                    </div>

                    <a href="/?uid={uid}" class="btn btn-primary btn-block">
                        Continue to Settings
                    </a>

                    <div class="card">
                        <h3>Ready to Go!</h3>
                        <p>You can now check your Whoop data by chatting with Omi.</p>
                        <p>Try: <strong>"What's my recovery today?"</strong></p>
                    </div>

                    <div class="footer">Powered by <strong>Omi</strong></div>
                </div>
            </body>
        </html>
        """)

    except Exception as e:
        log(f"OAuth error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"Authentication error: {str(e)}", status_code=500)


@app.get("/setup/whoop")
async def check_setup(uid: str = Query(...)):
    """Check if user has completed Whoop setup."""
    tokens = get_whoop_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect(uid: str = Query(...)):
    """Disconnect Whoop."""
    delete_whoop_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "whoop-omi"}


# ============================================
# CSS Styles
# ============================================

def get_css() -> str:
    """Returns Whoop-inspired dark theme CSS."""
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d0d0d;
            color: #ffffff;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 600px; margin: 0 auto; }
        .icon { font-size: 64px; text-align: center; margin-bottom: 20px; }
        h1 { color: #fff; font-size: 28px; text-align: center; margin-bottom: 8px; }
        h2 { color: #fff; font-size: 22px; margin-bottom: 12px; }
        h3 { color: #fff; font-size: 18px; margin-bottom: 12px; }
        p { color: #8c8c8c; text-align: center; margin-bottom: 24px; }
        .card {
            background: #1a1a1a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            border: 1px solid #333;
        }
        .btn {
            display: inline-block;
            padding: 14px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            border: none;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .btn-primary {
            background: linear-gradient(135deg, #00d9ff 0%, #00a8cc 100%);
            color: #000;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #00f0ff 0%, #00bfdf 100%);
        }
        .btn-secondary {
            background: transparent;
            color: #8c8c8c;
            border: 1px solid #333;
        }
        .btn-secondary:hover { background: #1a1a1a; }
        .btn-block { display: block; width: 100%; margin: 12px 0; }
        .success-box {
            background: rgba(0, 217, 143, 0.1);
            border: 1px solid #00d98f;
            border-radius: 12px;
            padding: 32px;
            text-align: center;
            margin-bottom: 24px;
        }
        .success-box h2 { color: #00d98f; }
        .error-box {
            background: rgba(255, 59, 48, 0.1);
            border: 1px solid #ff3b30;
            border-radius: 12px;
            padding: 32px;
            text-align: center;
        }
        .error-box h2 { color: #ff3b30; }
        ul { list-style: none; padding: 0; }
        li { padding: 10px 0; border-bottom: 1px solid #333; }
        li:last-child { border-bottom: none; }
        .example {
            background: #0d0d0d;
            padding: 12px 16px;
            border-radius: 8px;
            margin: 8px 0;
            font-style: italic;
            color: #8c8c8c;
            border: 1px solid #333;
        }
        .footer {
            text-align: center;
            color: #555;
            margin-top: 40px;
            padding: 20px;
            font-size: 14px;
        }
        .footer strong { color: #00d9ff; }
        @media (max-width: 480px) {
            body { padding: 12px; }
            .card { padding: 18px; }
            h1 { font-size: 24px; }
        }
    """


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    print("Whoop Omi Integration")
    print("=" * 50)
    print(f"Starting on {host}:{port}")
    print("=" * 50)

    uvicorn.run("main:app", host=host, port=port, reload=True)
