import json
import logging

from openai import AsyncOpenAI

from app.config import (
    OPENROUTER_API_KEY,
    LLM_MODEL,
    SYSTEM_PROMPT,
    NOTIFY_CONFIDENCE_THRESHOLD,
    TASK_CONFIDENCE_THRESHOLD,
    MEMORY_CONFIDENCE_THRESHOLD,
)
from app import omi_client

log = logging.getLogger('uvicorn.error')


_client = AsyncOpenAI(
    base_url='https://openrouter.ai/api/v1',
    api_key=OPENROUTER_API_KEY,
)

# Static system message — identical across all calls, enabling prompt caching.
# Providers like DeepSeek and Gemini cache matching prefixes automatically.
# Anthropic models on OpenRouter use cache_control breakpoints.
_system_messages = [
    {
        'role': 'system',
        'content': [
            {
                'type': 'text',
                'text': SYSTEM_PROMPT,
                'cache_control': {'type': 'ephemeral'},
            }
        ],
    }
]


async def process_and_decide(segments: list[dict], session_id: str) -> dict | None:
    transcript = '\n'.join(
        f"{'User' if s.get('is_user') else 'Other'}: {s.get('text', '')}" for s in segments
    )

    # Dynamic part — only this changes per call
    messages = _system_messages + [{'role': 'user', 'content': transcript}]

    try:
        response = await _client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            response_format={'type': 'json_object'},
        )
    except Exception as e:
        log.error(f'LLM call failed: {e}')
        return None

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(f'LLM returned invalid JSON: {raw}')
        return None

    # --- Tasks ---
    for task in result.get('tasks', []):
        desc = task.get('description', '').strip()
        confidence = float(task.get('confidence', 0))
        if not desc:
            continue
        if confidence < TASK_CONFIDENCE_THRESHOLD:
            log.info(f'Task skipped (confidence {confidence:.2f} < {TASK_CONFIDENCE_THRESHOLD}): {desc}')
            continue
        await omi_client.create_task(session_id, desc, task.get('due_at'))

    # --- Memories ---
    for mem in result.get('memories', []):
        content = mem.get('content', '').strip()
        confidence = float(mem.get('confidence', 0))
        if not content:
            continue
        if confidence < MEMORY_CONFIDENCE_THRESHOLD:
            log.info(f'Memory skipped (confidence {confidence:.2f} < {MEMORY_CONFIDENCE_THRESHOLD}): {content}')
            continue
        await omi_client.create_memory(session_id, content, mem.get('tags', []))

    # --- Notification ---
    notify_confidence = float(result.get('notify_confidence', 0))
    if result.get('should_notify') and notify_confidence >= NOTIFY_CONFIDENCE_THRESHOLD:
        return {
            'message': result.get('message', ''),
            'notification': {
                'prompt': result.get('message', ''),
                'params': ['user_name'],
            },
        }
    elif result.get('should_notify'):
        log.info(
            f'Notification skipped (confidence {notify_confidence:.2f} < {NOTIFY_CONFIDENCE_THRESHOLD}): '
            f'{result.get("message", "")}'
        )

    return None
