import os
import logging
import logging.config
import shutil
from datetime import datetime

def setup_logging():
    """
    Configure and set up logging for the application.
    Creates logs directory, handles log rotation, and configures logging levels.
    """
    # Set up logging directory structure
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    log_file = os.path.join(logs_dir, "debug.log")

    # Create logs directory
    os.makedirs(logs_dir, exist_ok=True)

    # Backup existing log file if it exists
    if os.path.exists(log_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(logs_dir, f"debug_{timestamp}.log")
        try:
            shutil.copy2(log_file, backup_file)
            print(f"Backed up log file to {backup_file}")
            # Clear the existing log file
            with open(log_file, 'w') as f:
                f.write(f"--- New log started at {datetime.now()} ---\n")
        except Exception as e:
            print(f"Warning: Could not backup log file: {e}")

    # Configure logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
            },
            "detailed": {
                "format": "[%(asctime)s] [%(name)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": LOG_LEVEL,
                "formatter": "standard",
            },
            "file": {
                "class": "logging.FileHandler",
                "level": LOG_LEVEL,
                "formatter": "detailed",
                "filename": log_file,
                "encoding": "utf8"
            }
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
            },
            "stt.streaming": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            "routers.transcribe": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            "uvicorn.error": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            "deepgram": {
                "handlers": ["console", "file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
        }
    }

    # Apply logging configuration
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")

    return logger