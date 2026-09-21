import logging

# Configure a module‑level logger for the plugin.
logger = logging.getLogger("omi_slack_app")
if not logger.handlers:
    # Prevent duplicate handlers in case of multiple imports.
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
