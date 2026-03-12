"""Mock utils.conversations.process_conversation — slow stub (THE key leak amplifier).

This runs inside _process_conversation_task which is fire-and-forget via safe_create_task.
The sleep keeps the task (and its websocket reference) alive, amplifying leak 1.

Improvement #8: Configurable sleep via PROCESS_CONVERSATION_SLEEP env var.
"""

import os
import time

_SLEEP_SECONDS = float(os.environ.get('PROCESS_CONVERSATION_SLEEP', '5.0'))


def process_conversation(uid, language, conversation):
    """Block for N seconds — this is called via asyncio.to_thread, so it blocks a thread."""
    time.sleep(_SLEEP_SECONDS)
    return conversation
