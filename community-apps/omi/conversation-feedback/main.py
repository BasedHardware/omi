"""
Conversation Feedback App

Analyzes completed conversations and provides actionable feedback to help users
improve their communication skills. Only sends notifications for important insights.
"""

from fastapi import APIRouter
from langchain_openai import ChatOpenAI

# Import from parent plugins module
import sys
from pathlib import Path

# Add plugins/example to path for imports
plugins_path = Path(__file__).parent.parent.parent.parent / 'plugins' / 'example'
sys.path.insert(0, str(plugins_path))

from models import Conversation, EndpointResponse
from utils import num_tokens_from_string

router = APIRouter()
chat = ChatOpenAI(model='gpt-4o', temperature=0)


@router.post('/conversation-feedback', tags=['conversation-feedback'], response_model=EndpointResponse)
def conversation_feedback(conversation: Conversation):
    """
    Analyzes a completed conversation and provides feedback.

    Only sends notification if the feedback is important enough to warrant
    interrupting the user. Uses GPT-4 to determine relevance and generate
    concise, actionable insights.

    Args:
        conversation: The completed conversation with transcript and structured data

    Returns:
        EndpointResponse with feedback message (empty if not important)
    """
    prompt = f'''
      The following is the structuring from a transcript of a conversation that just finished.
      First determine if there's crucial feedback to notify a busy entrepreneur about it.
      If not, simply output an empty string, but if it is important, output 20 words (at most) with the most important feedback for the conversation.
      Be short, concise, and helpful, and specially strict on determining if it's worth notifying or not.
      Also, act human-like, friendly, and address the user directly. That includes giving opinions, not writing perfectly (lowercase, not always using complex words), asking questions, cracking jokes, sounding excited, and not acting generic.

      Transcript:
      ${conversation.get_transcript()}

      Structured version:
      ${conversation.structured.dict()}

      Answer:
    '''

    # Skip if conversation is too long (edge case protection)
    if num_tokens_from_string(prompt) > 10000:
        return {'message': ''}

    # Get AI feedback
    response = chat.invoke(prompt)

    # Only return message if it's substantial (at least 5 characters)
    return {'message': '' if len(response.content) < 5 else response.content}
