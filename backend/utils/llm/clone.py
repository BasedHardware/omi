from utils.llm.clients import get_llm
from utils.llms.memory import get_prompt_memories
from utils.llm.usage_tracker import track_usage, Features
import logging

logger = logging.getLogger(__name__)


def generate_clone_reply(
    uid: str, sender: str, message: str, platform: str, conversation_history: list[dict] | None = None
) -> str:
    """Generate a reply in the user's voice based on their memories and communication style."""
    user_name, memories_str = get_prompt_memories(uid)

    history_str = ''
    if conversation_history:
        history_lines = []
        for turn in conversation_history[-6:]:
            role = sender if turn.get('role') == 'user' else user_name
            history_lines.append(f'{role}: {turn.get("content", "")}')
        history_str = '\n'.join(history_lines) + '\n'

    platform_context = {
        'imessage': 'iMessage (casual, personal)',
        'telegram': 'Telegram (informal messaging)',
        'whatsapp': 'WhatsApp (casual messaging)',
    }.get(platform, platform)

    prompt = f"""You are roleplaying as {user_name}. Write a reply to a message they received on {platform_context}.

What you know about {user_name}:
{memories_str}

{'Recent conversation:\n' + history_str if history_str else ''}Message from {sender}:
"{message}"

Write a reply exactly as {user_name} would send it. Rules:
- Match their natural tone and vocabulary (casual, not formal)
- Be concise — 1-3 sentences typical for messaging apps
- Do NOT start with their name, greetings, or "Hi" unless it fits naturally
- Sound like a real person texting, not an AI assistant
- Only output the reply text itself, nothing else"""

    with track_usage(uid, Features.CHAT):
        return get_llm('chat_responses').invoke(prompt).content.strip()
