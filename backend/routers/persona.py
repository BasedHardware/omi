import json
import os
from fastapi import APIRouter, Depends, Form, UploadFile, File
from datetime import datetime
from ulid import ULID
from database.facts import get_facts
from database.auth import get_user_name
from database.memories import get_memories
from models.memory import Memory
from utils.llm import llm_medium
from utils.other import endpoints as auth
from database._client import db
from utils.other.storage import upload_plugin_logo

router = APIRouter()


def generate_description(facts):
    # Create a concise description from facts
    facts_text = "\n".join([f"- {fact['content']}" for fact in facts if not fact['deleted']])

    prompt = f"""Based on these facts about a person, create a concise, engaging description that captures their unique personality and characteristics (max 250 characters).

Facts:
{facts_text}

Create a natural, memorable description that captures this person's essence. Focus on the most unique and interesting aspects. Make it conversational and engaging."""

    try:
        response = llm_medium.invoke(prompt)
        description = response.content
        return description
    except Exception as e:
        print(f'Error generating description: {e}')
        # Fallback to simple description if API call fails
        key_facts = [fact['content'] for fact in facts if not fact['deleted']][:3]
        facts_summary = ". ".join(key_facts)
        return facts_summary[:250]


@router.post("/v1/persona")
async def create_persona(persona_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(persona_data)
    # get facts from db
    facts = get_facts(uid, limit=1000)
    # get firebase user name from uid
    user_name = get_user_name(uid)

    # get the most recent 50 memories from db and convert them to a single string
    memories = get_memories(uid, limit=50)
    conversation_history = Memory.memories_to_string(memories)

    # Create the chat prompt template
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
    facts_text = "\n".join([f"- {fact['content']}" for fact in facts if not fact['deleted']])
    chat_prompt += f"\n{facts_text}"

    # Add conversation history
    chat_prompt += "\n\nRecent Conversations:\n" + conversation_history

    # Add final instructions
    chat_prompt += "\n\nUse these facts and conversations to shape your personality. Responses should help the conversation go deeper. You have strong opinions, slightly controversial."

    # Generate persona description
    description = generate_description(facts)

    # Upload image to omi_plugins_bucket
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    # Use the provided doc_id from the request data
    doc_id = str(ULID())
    imgUrl = upload_plugin_logo(file_path, doc_id)

    # Save persona data to Firestore at the specified document ID
    doc_ref = db.collection('plugins_data').document(doc_id).set({
        'approved': True,
        'author': data['author'],
        'capabilities': ["chat"],
        'category': 'persona',
        'chat_prompt': chat_prompt,
        'connected_accounts': ["omi"],
        'created_at': datetime.now().isoformat(),
        'deleted': False,
        'description': description,
        'email': data['email'],
        'id': doc_id,
        'image': imgUrl,
        'name': user_name,
        'private': True,
        'status': 'approved',
        'uid': uid
    })

    return {
        "chat_prompt": chat_prompt,
        "description": description,
        "doc_id": doc_id
    }
