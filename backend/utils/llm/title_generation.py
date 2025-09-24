import re
from typing import Optional
from .clients import llm_title_generator
from langchain_core.messages import HumanMessage


def generate_thread_title(first_message: str) -> str:
    """
    Generate a concise title for a chat thread with enhanced input validation.
    Uses GPT-4o-mini for fast, lightweight title generation.

    Args:
        first_message: The first message sent by the user in the thread

    Returns:
        A concise, clean title for the thread
    """
    # Input validation and cleaning
    if not first_message or not first_message.strip():
        return "New Chat"

    # Clean and truncate input message
    cleaned_message = _clean_input_message(first_message)
    if not cleaned_message:
        return "New Chat"

    try:
        prompt = f"""Generate a very short, concise title (3-6 words max) for a chat conversation that starts with this message:

"{cleaned_message}"

Rules:
- Maximum 6 words
- No quotes or punctuation  
- Capture the main topic or intent
- Make it descriptive and clear

Title:"""

        response = llm_title_generator.invoke([HumanMessage(content=prompt)])
        title = response.content.strip()

        # Enhanced cleaning and validation
        cleaned_title = _clean_and_validate_title(title)

        return cleaned_title if cleaned_title else "New Chat"

    except Exception as e:
        print(f"Error generating thread title: {e}")
        return "New Chat"


def _clean_input_message(message: str) -> Optional[str]:
    """Clean and validate input message before sending to LLM."""
    if not message:
        return None

    # Strip and normalize whitespace
    message = ' '.join(message.strip().split())

    # Truncate very long messages (keep first 500 chars for context)
    if len(message) > 500:
        message = message[:500] + "..."

    # Check for reasonable content length
    if len(message.strip()) < 3:
        return None

    return message


def _clean_and_validate_title(title: str) -> Optional[str]:
    """Clean and validate the generated title."""
    if not title:
        return None

    # Remove quotes and excessive punctuation
    title = re.sub(r'["\']', '', title)
    title = re.sub(r'[^\w\s-]', ' ', title)  # Keep only words, spaces, hyphens
    title = ' '.join(title.split())  # Normalize whitespace

    # Length validation
    words = title.split()
    if len(words) > 6:
        title = ' '.join(words[:6])

    # Character limit fallback
    if len(title) > 50:
        title = title[:47] + "..."

    # Minimum length check
    if len(title.strip()) < 3:
        return None

    # Capitalize properly
    return title.title()
