import logging
from pathlib import Path

# Create a logger for the Slack app plugin
logger = logging.getLogger("omi_slack_app")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    log_path = Path(__file__).resolve().parent / "slack_app.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
