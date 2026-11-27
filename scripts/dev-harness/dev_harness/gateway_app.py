"""LLM gateway entrypoint used only when log timestamps are switched on.

Importing this module imports the gateway, so only uvicorn loads it. See
``dev_harness.log_timestamps``; without the switch the harness starts
``llm_gateway.main:app`` directly, as before.
"""

from __future__ import annotations

from dev_harness import log_timestamps
from llm_gateway.main import app

log_timestamps.install()

__all__ = ["app"]
