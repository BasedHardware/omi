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
import re
import subprocess

logger = logging.getLogger(__name__)

_MARKER_RE = re.compile(r'<<<DRAFT>>>(.*?)<<<END>>>', re.S)


def local_cli_llm_text(prompt: str) -> str | None:
    cli = os.getenv('OMI_LOCAL_LLM_CLI')
    if not cli:
        return None
    # Agentic CLIs (e.g. Claude Code) tend to add preamble/commentary. Force the
    # answer into explicit markers and extract only that, so the caller gets the
    # raw message with no agent chatter.
    wrapped = (
        prompt + "\n\nOutput format — CRITICAL: reply with ONLY the final message text, wrapped exactly as:\n"
        "<<<DRAFT>>>the message here<<<END>>>\n"
        "No preamble, no explanation, no reasoning — just the wrapped message."
    )
    try:
        result = subprocess.run([cli, '-p', wrapped], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning(f"local_cli_llm_text: {cli} rc={result.returncode}")
            return None
        out = (result.stdout or '').strip()
        if not out:
            return None
        match = _MARKER_RE.search(out)
        if match:
            return match.group(1).strip() or None
        # Fallback: no markers — take the last non-empty paragraph (drops any preamble).
        paras = [p.strip() for p in out.split('\n\n') if p.strip()]
        return (paras[-1] if paras else out) or None
    except Exception as e:
        logger.warning(f"local_cli_llm_text error: {e}")
        return None
