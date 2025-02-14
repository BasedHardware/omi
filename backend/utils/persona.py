import os
from datetime import datetime

from database.apps import update_persona_in_db, get_persona_by_uid_db
from database.facts import get_facts
from database.auth import get_user_name
from database.memories import get_memories
from database._client import db
from models.memory import Memory
from routers.persona import condense_facts, condense_conversations


def update_persona_prompt(uid: str, doc_id: str):
    """Update a persona's chat prompt with latest facts and memories."""
    # Get latest facts and user info
    facts = get_facts(uid, limit=1000)
    user_name = get_user_name(uid)
    
    # Get and condense recent memories
    memories = get_memories(uid, limit=100)
    conversation_history = Memory.memories_to_string(memories)
    conversation_history = condense_conversations([conversation_history])
    
    # Condense facts
    facts_text = condense_facts([fact['content'] for fact in facts if not fact['deleted']])
    
    # Generate updated chat prompt
    chat_prompt = f"""You are {user_name} AI, you must personify {user_name} as well as you can.

Style:
- Interactive highly opinionated messages and questions.
- Reference your personal facts naturally

Rules:
- Never mention being AI
- No ** or formal language
- 2-3 sentences for response. Never more than 20 words.
- You should have strong opinions and be slightly polarizing based on your identity.
- You must make the conversation flow. You excel at coherent conversations.

Personal Facts and Context:
{facts_text}

Recent Conversations:
{conversation_history}

Use these facts and conversations to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."""

    persona = get_persona_by_uid_db(uid)
    persona['chat_prompt'] = chat_prompt
    persona['updated_at'] = datetime.utcnow()
    update_persona_in_db(persona)