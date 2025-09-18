from .clients import llm_title_generator
from langchain_core.messages import HumanMessage


def generate_thread_title(first_message: str) -> str:
    """
    Generate a concise title for a chat thread based on the first user message.
    Uses GPT-4o-mini for fast, lightweight title generation.

    Args:
        first_message: The first message sent by the user in the thread

    Returns:
        A concise title (max 20 tokens) for the thread
    """
    try:
        prompt = f"""Generate a very short, concise title (3-6 words max) for a chat conversation that starts with this message:

"{first_message}"

Rules:
- Maximum 6 words
- No quotes or punctuation  
- Capture the main topic or intent
- Make it descriptive and clear

Title:"""

        response = llm_title_generator.invoke([HumanMessage(content=prompt)])
        title = response.content.strip()

        # Clean up the title - remove quotes, extra whitespace, etc.
        title = title.replace('"', '').replace("'", "").strip()

        # Ensure it's not too long (fallback)
        words = title.split()
        if len(words) > 6:
            title = ' '.join(words[:6])

        return title if title else "New Chat"

    except Exception as e:
        print(f"Error generating thread title: {e}")
        return "New Chat"
