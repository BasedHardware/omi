from __future__ import annotations

import os

LLM_GATEWAY_URL_ENV_VAR = 'OMI_LLM_GATEWAY_URL'
DEFAULT_LLM_GATEWAY_URL = 'http://127.0.0.1:9080'
LLM_GATEWAY_AUTO_LANE_PREFIX = 'omi:auto:'


def get_llm_gateway_base_url() -> str:
    configured = os.getenv(LLM_GATEWAY_URL_ENV_VAR, '').strip()
    return configured.rstrip('/') if configured else DEFAULT_LLM_GATEWAY_URL


def is_auto_lane_id(model_or_lane: object) -> bool:
    return isinstance(model_or_lane, str) and model_or_lane.startswith(LLM_GATEWAY_AUTO_LANE_PREFIX)
