```python
import logging

logger = logging.getLogger(__name__)

def get_apple_health_steps_tool():
    try:
        # Existing code to retrieve steps
        return "The steps were retrieved successfully."
    except Exception as e:
        logger.error(f"Error in get_apple_health_steps_tool: {{e}}", exc_info=True)
        return "An unexpected error occurred while retrieving step data. Please try again later."

def get_apple_health_sleep_tool():
    try:
        # Existing code to retrieve sleep data
        return "The sleep data was retrieved successfully."
    except Exception as e:
        logger.error(f"Error in get_apple_health_sleep_tool: {{e}}", exc_info=True)
        return "An unexpected error occurred while retrieving sleep data. Please try again later."

def get_apple_health_heart_rate_tool():
    try:
        # Existing code to retrieve heart rate data
        return "The heart rate data was retrieved successfully."
    except Exception as e:
        logger.error(f"Error in get_apple_health_heart_rate_tool: {{e}}", exc_info=True)
        return "An unexpected error occurred while retrieving heart rate data. Please try again later."

def get_apple_health_workouts_tool():
    try:
        # Existing code to retrieve workout data
        return "The workout data was retrieved successfully."
    except Exception as e:
        logger.error(f"Error in get_apple_health_workouts_tool: {{e}}", exc_info=True)
        return "An unexpected error occurred while retrieving workout data. Please try again later."

def get_apple_health_summary_tool():
    try:
        # Existing code to retrieve summary data
        return "The summary data was retrieved successfully."
    except Exception as e:
        logger.error(f"Error in get_apple_health_summary_tool: {{e}}", exc_info=True)
        return "An unexpected error occurred while retrieving summary data. Please try again later."
```