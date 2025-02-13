import os
from typing import List, Optional

from openai import AsyncClient

from models.app import App
from models.chat import Message

openrouter_key = os.getenv('OPENROUTER_API_KEY')

client = AsyncClient(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_key,
)


async def execute_persona_chat_stream(uid: str, messages: List[Message], app: App, cited: Optional[bool] = False,
                                      callback_data: dict = None):
    """Handle streaming chat responses for persona-type apps using OpenRouter."""

    system_prompt = app.chat_prompt
    formatted_messages = [{
        "role": "system",
        "content": system_prompt
    }]

    # Add message history
    for msg in messages:
        role = "assistant" if msg.sender == "ai" else "user"
        formatted_messages.append({"role": role, "content": msg.text})

    # Track the full response for callback_data
    full_response = []

    # Stream the response
    try:
        stream = await client.chat.completions.create(
            messages=formatted_messages,
            model="google/gemini-flash-1.5-8b",
            stream=True
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response.append(content)
                data = content.replace("\n", "__CRLF__")
                yield f"data: {data}\n\n"

        # Store final response in callback_data
        if callback_data is not None:
            callback_data['answer'] = ''.join(full_response)
            callback_data['memories_found'] = []
            callback_data['ask_for_nps'] = False

    except Exception as e:
        print(f"Error in execute_persona_chat_stream: {e}")
        if callback_data is not None:
            callback_data['error'] = str(e)

    yield None
