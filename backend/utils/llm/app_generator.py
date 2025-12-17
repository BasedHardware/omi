"""
AI App Generator utility
Generates app configuration from a natural language prompt using LLM
"""

import json
import base64
import httpx
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI

from utils.llm.clients import llm_medium, llm_mini


# App categories available in the system
APP_CATEGORIES = [
    {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
    {'title': 'Personality Clone', 'id': 'personality-emulation'},
    {'title': 'Health', 'id': 'health-and-wellness'},
    {'title': 'Education', 'id': 'education-and-learning'},
    {'title': 'Communication', 'id': 'communication-improvement'},
    {'title': 'Emotional Support', 'id': 'emotional-and-mental-support'},
    {'title': 'Productivity', 'id': 'productivity-and-organization'},
    {'title': 'Entertainment', 'id': 'entertainment-and-fun'},
    {'title': 'Financial', 'id': 'financial'},
    {'title': 'Travel', 'id': 'travel-and-exploration'},
    {'title': 'Safety', 'id': 'safety-and-security'},
    {'title': 'Shopping', 'id': 'shopping-and-commerce'},
    {'title': 'Social', 'id': 'social-and-relationships'},
    {'title': 'News', 'id': 'news-and-information'},
    {'title': 'Utilities', 'id': 'utilities-and-tools'},
    {'title': 'Other', 'id': 'other'},
]


class GeneratedAppData(BaseModel):
    """Structure for AI-generated app data"""

    name: str
    description: str
    category: str
    capabilities: list[str]  # 'chat' or 'memories' or both
    chat_prompt: Optional[str] = None
    memory_prompt: Optional[str] = None


SYSTEM_PROMPT = """You are an expert app designer for Omi, an AI-powered wearable device that records conversations and provides intelligent insights.

Your task is to design an app based on the user's description. Apps in Omi can have two main capabilities:

1. **Chat Apps** (capability: "chat"): These apps allow users to chat with an AI persona or assistant. They require a `chat_prompt` that defines the personality, expertise, and behavior of the chat assistant. Chat apps are great for:
   - AI personas (like cloning a celebrity or expert)
   - Specialized assistants (coaches, tutors, advisors)
   - Interactive conversations about specific topics

2. **Conversation/Memory Apps** (capability: "memories"): These apps analyze user conversations and generate insights or summaries. They require a `memory_prompt` that tells the AI what to extract or analyze from conversations. Memory apps are great for:
   - Summarizing conversations into specific formats
   - Extracting action items, decisions, or key points
   - Organizing information into structures (like mind maps, bullet points)
   - Tracking specific topics over time

An app can have BOTH capabilities if it makes sense (e.g., an app that analyzes conversations AND allows chatting about the analysis).

Available categories (pick the most appropriate one):
{categories}

IMPORTANT GUIDELINES:
- Write prompts that are detailed and specific
- For chat_prompt: Define the persona's personality, expertise, speaking style, and what they should help with
- For memory_prompt: Be specific about what information to extract, how to format it, and what insights to provide
- Choose capabilities based on what the user is asking for:
  - If they want to "talk to" or "chat with" something → include "chat"
  - If they want to "analyze", "summarize", "organize", or "extract" from conversations → include "memories"
  - If both make sense, include both

Return your response as a valid JSON object with this exact structure:
{{
    "name": "App Name (short, catchy, max 30 chars)",
    "description": "A compelling description of what the app does (50-150 words)",
    "category": "category-id from the list above",
    "capabilities": ["chat", "memories"],  // include relevant ones
    "chat_prompt": "Detailed prompt for chat persona (only if chat capability is included)",
    "memory_prompt": "Detailed prompt for conversation analysis (only if memories capability is included)"
}}

Only include chat_prompt if "chat" is in capabilities.
Only include memory_prompt if "memories" is in capabilities."""


async def generate_app_from_prompt(user_prompt: str) -> GeneratedAppData:
    """
    Generate app configuration from a natural language prompt using LLM.

    Args:
        user_prompt: The user's description of what kind of app they want

    Returns:
        GeneratedAppData with all the app configuration
    """
    categories_str = "\n".join([f"- {cat['title']} (id: {cat['id']})" for cat in APP_CATEGORIES])

    system_message = SYSTEM_PROMPT.format(categories=categories_str)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"Create an app based on this description:\n\n{user_prompt}"},
    ]

    response = await llm_medium.ainvoke(messages)

    # Parse the JSON response
    content = response.content.strip()

    # Handle potential markdown code blocks
    if content.startswith("```"):
        # Remove markdown code block markers
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    try:
        app_data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        import re

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            app_data = json.loads(json_match.group())
        else:
            raise ValueError("Failed to parse LLM response as JSON")

    # Validate and construct the response
    return GeneratedAppData(
        name=app_data.get("name", "My App")[:50],
        description=app_data.get("description", "An AI-powered app"),
        category=app_data.get("category", "other"),
        capabilities=app_data.get("capabilities", ["chat"]),
        chat_prompt=app_data.get("chat_prompt") if "chat" in app_data.get("capabilities", []) else None,
        memory_prompt=app_data.get("memory_prompt") if "memories" in app_data.get("capabilities", []) else None,
    )


async def generate_app_icon(app_name: str, app_description: str, category: str) -> bytes:
    """
    Generate an app icon using OpenAI's DALL-E.

    Args:
        app_name: Name of the app
        app_description: Description of the app
        category: Category of the app

    Returns:
        PNG image bytes of the generated icon
    """
    client = OpenAI()

    # Create a prompt for icon generation
    icon_prompt = f"""Create a modern, minimal app icon for an AI app called "{app_name}".

App description: {app_description}
Category: {category}

Design requirements:
- Clean, minimal design with a single focal element
- Modern gradient or solid color background
- Simple geometric shapes or abstract representation
- Professional and polished look
- Should work well at small sizes (app icon)
- No text or letters in the icon
- Vibrant but not overwhelming colors
- Style: Similar to modern iOS/Android app icons"""

    response = client.images.generate(
        model="dall-e-3", prompt=icon_prompt, size="1024x1024", quality="standard", n=1, response_format="b64_json"
    )

    # Get the base64 image data and decode it
    image_data = response.data[0].b64_json
    return base64.b64decode(image_data)


async def download_image_from_url(url: str) -> bytes:
    """Download image from URL and return bytes."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def generate_description(app_name: str, description: str) -> str:
    """
    Generate an improved app description from a basic one.
    Used by the app submission flow.
    """
    prompt = f"""
    You are an AI assistant specializing in crafting detailed and engaging descriptions for apps.
    You will be provided with the app's name and a brief description which might not be that good. Your task is to expand on the given information, creating a captivating and detailed app description that highlights the app's features, functionality, and benefits.
    The description should be concise, professional, and not more than 40 words, ensuring clarity and appeal. Respond with only the description, tailored to the app's concept and purpose.
    App Name: {app_name}
    Description: {description}
    """
    prompt = prompt.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


def generate_description_and_emoji(app_name: str, prompt: str) -> dict:
    """
    Generate an app description and a representative emoji for the app.
    Used by the quick template creator feature.
    """
    system_prompt = """You are an AI assistant that creates app descriptions and selects representative emojis.

Given an app name and what it should do, respond with a JSON object containing:
1. "description": A concise, engaging description (max 40 words) highlighting what the app does
2. "emoji": A single emoji that best represents the app's purpose

Respond ONLY with the JSON object, no other text."""

    user_prompt = f"""App Name: {app_name}
What it does: {prompt}"""

    response = llm_mini.invoke([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])

    content = response.content.strip()

    # Parse JSON from response
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        result = json.loads(content)
        return {
            "description": result.get("description", f"A custom app that {prompt}"),
            "emoji": result.get("emoji", "✨"),
        }
    except (json.JSONDecodeError, KeyError):
        # Fallback if JSON parsing fails
        return {"description": f"A custom app that {prompt}", "emoji": "✨"}
