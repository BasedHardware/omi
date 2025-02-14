import json
import os
from fastapi import APIRouter, Depends, Form, UploadFile, File
from datetime import datetime
from ulid import ULID

from database.apps import add_persona_to_db
from database.facts import get_facts
from database.auth import get_user_name
from database.memories import get_memories
from models.memory import Memory
from utils.llm import condense_conversations, condense_facts, generate_persona_description
from utils.other import endpoints as auth
from utils.other.storage import upload_plugin_logo

router = APIRouter()


@router.post("/v1/persona")
async def create_persona(persona_data: str = Form(...), file: UploadFile = File(...),
                         uid=Depends(auth.get_current_user_uid)):
    data = json.loads(persona_data)
    facts = get_facts(uid, limit=1000)
    user_name = get_user_name(uid)

    memories = get_memories(uid, limit=100)
    conversation_history = Memory.memories_to_string(memories)
    conversation_history = condense_conversations([conversation_history])

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

Personal Facts and Context:"""

    # Add user facts to the prompt
    facts_text = condense_facts([fact['content'] for fact in facts if not fact['deleted']])
    chat_prompt += f"\n{facts_text}"

    # Add conversation history
    chat_prompt += "\n\nRecent Conversations:\n" + conversation_history

    # Add final instructions
    chat_prompt += "\n\nUse these facts and conversations to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."

    # Generate persona description
    description = generate_persona_description(facts_text)

    # Upload image to omi_plugins_bucket
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    persona_id = str(ULID())
    img_url = upload_plugin_logo(file_path, persona_id)

    doc_data = {
        'approved': False,
        'author': data['author'],
        'capabilities': ["chat", "persona"],
        'category': 'persona',
        'chat_prompt': chat_prompt,
        'connected_accounts': ["omi"],
        'created_at': datetime.now().isoformat(),
        'deleted': False,
        'description': description,
        'email': data['email'],
        'id': persona_id,
        'image': img_url,
        'name': user_name,
        'private': data['private'],
        'status': 'under-review',
        'uid': uid
    }
    add_persona_to_db(doc_data)
    return {'success': True, 'message': 'Persona created successfully.'}
