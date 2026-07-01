"""
Local-development LLM shim.

When `OMI_LOCAL_LLM_CLI` is set (local dev only — never in production), text
generation can be produced by shelling out to that CLI (e.g. the `claude` CLI)
instead of a hosted provider. This lets the backend run end-to-end on a machine
that has no OpenAI/Gemini API key. Returns None when unconfigured so callers fall
back to the normal `get_llm(...)` path — so production behavior is unchanged.
"""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def local_cli_llm_text(prompt: str) -> str | None:
    cli = os.getenv('OMI_LOCAL_LLM_CLI')
    if not cli:
        return None
    try:
        result = subprocess.run([cli, '-p', prompt], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning(f"local_cli_llm_text: {cli} rc={result.returncode}")
            return None
        text = (result.stdout or '').strip()
        return text or None
    except Exception as e:
        logger.warning(f"local_cli_llm_text error: {e}")
        return None
