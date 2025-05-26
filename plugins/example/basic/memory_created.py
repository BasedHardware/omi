from fastapi import APIRouter
from langchain_openai import ChatOpenAI

from models import Memory, EndpointResponse
from utils import num_tokens_from_string

router = APIRouter()
chat = ChatOpenAI(model='gpt-4o', temperature=0)


@router.post('/conversation-feedback', tags=['memory-created-example'], response_model=EndpointResponse)
def conversation_feedback(memory: Memory):
    prompt = f'''
      The following is the structuring from a transcript of a conversation that just finished.
      First determine if there's crucial feedback to notify a busy entrepreneur about it.
      If not, simply output an empty string, but if it is important, output 20 words (at most) with the most important feedback for the conversation.
      Be short, concise, and helpful, and specially strict on determining if it's worth notifying or not. 
      Also, act human-like, friendly, and address the user directly. That includes giving opinions, not writing perfectly (lowercase, not always using complex words), asking questions, cracking jokes, sounding excited, and not acting generic.

      Transcript:
      ${memory.get_transcript()}
      
      Structured version:
      ${memory.structured.dict()}

      Answer:
    '''
    if num_tokens_from_string(prompt) > 10000:  # unless you are transcribing a podcast, this should never happen
        return {}

    response = chat.invoke(prompt)
    return {'message': '' if len(response.content) < 5 else response.content}
