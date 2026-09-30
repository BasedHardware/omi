```python
import logging
from typing import Optional

def format_error_for_tool(error: str) -> str:
    if error.startswith("The operation timed out"):
        return "The operation timed out. Please try again."
    return f"An error occurred while retrieving the data."

def get_apple_health_steps_tool() -> str:
    try:
        # Existing code to retrieve steps
        return "Apple Health Steps data retrieved successfully."
    except Exception as e:
        error_message = str(e)
        return format_error_for_tool(error_message)
    finally:
        logger.error("get_apple_health_steps_tool: error occurred", exc_info=True)

def get_apple_health_sleep_tool() -> str:
    try:
        # Existing code to retrieve sleep data
        return "Apple Health Sleep data retrieved successfully."
    except Exception as e:
        error_message = str(e)
        return format_error_for_tool(error_message)
    finally:
        logger.error("get_apple_health_sleep_tool: error occurred", exc_info=True)

def get_apple_health_heart_rate_tool() -> str:
    try:
        # Existing code to retrieve heart rate data
        return "Apple Health Heart Rate data retrieved successfully."
    except Exception as e:
        error_message = str(e)
        return format_error_for_tool(error_message)
    finally:
        logger.error("get_apple_health_heart_rate_tool: error occurred", exc_info=True)

def get_apple_health_workouts_tool() -> str:
    try:
        # Existing code to retrieve workout data
        return "Apple Health Workouts data retrieved successfully."
    except Exception as e:
        error_message = str(e)
        return format_error_for_tool(error_message)
    finally:
        logger.error("get_apple_health_workouts_tool: error occurred", exc_info=True)

def get_apple_health_summary_tool() -> str:
    try:
        # Existing code to retrieve summary data
        return "Apple Health Summary data retrieved successfully."
    except Exception as e:
        error_message = str(e)
        return format_error_for_tool(error_message)
    finally:
        logger.error("get_apple_health_summary_tool: error occurred", exc_info=True)
```