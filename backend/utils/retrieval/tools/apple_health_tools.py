import logging
from typing import Any, Dict, Optional
from datetime import datetime
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def get_apple_health_steps_tool(health_data: Dict[str, Any]) -> str:
    """Extract step count from Apple Health data."""
    try:
        steps = health_data.get('HKQuantityTypeIdentifierStepCount', {}).get('value', 0)
        return f"Today's step count: {steps}"
    except Exception as e:
        logger.error("Error in get_apple_health_steps_tool", exc_info=True)
        return "An unexpected error occurred while retrieving step data. Please try again later."

def get_apple_health_sleep_tool(health_data: Dict[str, Any]) -> str:
    """Extract sleep data from Apple Health data."""
    try:
        sleep_data = health_data.get('HKCategoryTypeIdentifierSleepAnalysis', {})
        if sleep_data:
            return f"Sleep duration: {sleep_data.get('value', 0)} minutes"
        return "No sleep data available."
    except Exception as e:
        logger.error("Error in get_apple_health_sleep_tool", exc_info=True)
        return "An unexpected error occurred while retrieving sleep data. Please try again later."

def get_apple_health_heart_rate_tool(health_data: Dict[str, Any]) -> str:
    """Extract heart rate data from Apple Health data."""
    try:
        heart_rate = health_data.get('HKQuantityTypeIdentifierHeartRate', {}).get('value', 0)
        return f"Current heart rate: {heart_rate} BPM"
    except Exception as e:
        logger.error("Error in get_apple_health_heart_rate_tool", exc_info=True)
        return "An unexpected error occurred while retrieving heart rate data. Please try again later."

def get_apple_health_workouts_tool(health_data: Dict[str, Any]) -> str:
    """Extract workout data from Apple Health data."""
    try:
        workouts = health_data.get('HKWorkoutActivityType', [])
        if workouts:
            return f"Workouts today: {len(workouts)} sessions"
        return "No workout data available."
    except Exception as e:
        logger.error("Error in get_apple_health_workouts_tool", exc_info=True)
        return "An unexpected error occurred while retrieving workout data. Please try again later."

def get_apple_health_summary_tool(health_data: Dict[str, Any]) -> str:
    """Generate a summary of Apple Health data."""
    try:
        steps = health_data.get('HKQuantityTypeIdentifierStepCount', {}).get('value', 0)
        heart_rate = health_data.get('HKQuantityTypeIdentifierHeartRate', {}).get('value', 0)
        return f"Health Summary: Steps - {steps}, Heart Rate - {heart_rate} BPM"
    except Exception as e:
        logger.error("Error in get_apple_health_summary_tool", exc_info=True)
        return "An unexpected error occurred while generating health summary. Please try again later."
