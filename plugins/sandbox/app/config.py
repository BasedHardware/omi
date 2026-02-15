import logging
import os
from pathlib import Path

log = logging.getLogger('uvicorn.error')

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
LLM_MODEL = os.getenv('LLM_MODEL', 'deepseek/deepseek-chat-v3-0324')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')
CHUNK_THRESHOLD = int(os.getenv('CHUNK_THRESHOLD', '10'))
TIME_THRESHOLD_SECONDS = int(os.getenv('TIME_THRESHOLD_SECONDS', '30'))

# Omi Integration API
OMI_API_URL = os.getenv('OMI_API_URL', 'https://api.omi.me')
OMI_APP_ID = os.getenv('OMI_APP_ID', '')
OMI_APP_API_KEY = os.getenv('OMI_APP_API_KEY', '')

# Confidence thresholds (0.0 to 1.0)
NOTIFY_CONFIDENCE_THRESHOLD = float(os.getenv('NOTIFY_CONFIDENCE_THRESHOLD', '0.8'))
TASK_CONFIDENCE_THRESHOLD = float(os.getenv('TASK_CONFIDENCE_THRESHOLD', '0.6'))
MEMORY_CONFIDENCE_THRESHOLD = float(os.getenv('MEMORY_CONFIDENCE_THRESHOLD', '0.5'))

# ---------------------------------------------------------------------------
# Prompt assembly — loaded once at startup, stays static for prompt caching.
#
# Layout:
#   prompts/system.md   — framework template (output format, confidence rules)
#   soul/identity.md    — app name & purpose         (edit this)
#   soul/tasks.md       — task extraction rules       (edit this)
#   soul/memories.md    — memory extraction rules     (edit this)
#   soul/notifications.md — notification rules        (edit this)
#   soul/personality.md — tone & style                (edit this)
#   soul/custom_rules.md — domain-specific logic      (edit this)
#
# The final string is identical across every API call → prompt cache hit.
# ---------------------------------------------------------------------------

_root = Path(__file__).resolve().parent.parent

_SOUL_FILES = [
    ('identity', 'soul/identity.md'),
    ('tasks', 'soul/tasks.md'),
    ('memories', 'soul/memories.md'),
    ('notifications', 'soul/notifications.md'),
    ('personality', 'soul/personality.md'),
    ('custom_rules', 'soul/custom_rules.md'),
]


def _load(rel_path: str) -> str:
    p = _root / rel_path
    if p.exists():
        return p.read_text().strip()
    log.warning(f'Missing prompt file: {p}')
    return ''


def _build_system_prompt() -> str:
    """Assemble the full system prompt from soul/ files + prompts/system.md."""
    soul = {key: _load(path) for key, path in _SOUL_FILES}
    template = _load('prompts/system.md')
    if not template:
        raise RuntimeError('prompts/system.md not found — cannot build system prompt')
    return template.format(**soul)


# Built once at import time. Never changes during runtime.
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT') or _build_system_prompt()
