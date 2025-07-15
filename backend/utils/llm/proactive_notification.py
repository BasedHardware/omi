from typing import List

from models.chat import Message
from utils.llm.clients import llm_mini
from utils.llms.memory import get_prompt_memories


def get_proactive_message(
    uid: str, plugin_prompt: str, params: [str], context: str, chat_messages: List[Message]
) -> str:
    user_name, memories_str = get_prompt_memories(uid)

    prompt = plugin_prompt
    for param in params:
        if param == "user_name":
            prompt = prompt.replace("{{user_name}}", user_name)
            continue
        if param == "user_facts":
            prompt = prompt.replace("{{user_facts}}", memories_str)
            continue
        if param == "user_context":
            prompt = prompt.replace("{{user_context}}", context if context else "")
            continue
        if param == "user_chat":
            prompt = prompt.replace(
                "{{user_chat}}", Message.get_messages_as_string(chat_messages) if chat_messages else ""
            )
            continue
    prompt = prompt.replace('    ', '').strip()
    # print(prompt)

    return llm_mini.invoke(prompt).content
