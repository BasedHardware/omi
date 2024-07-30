from fastapi import APIRouter
from langchain_openai import ChatOpenAI

from models import Memory, EndpointResponse

router = APIRouter()
chat = ChatOpenAI(model='gpt-4o', temperature=0)


@router.post('/conversation-feedback', tags=['basic', 'memory_created'], response_model=EndpointResponse)
def conversation_feedback(memory: Memory):
    response = chat.invoke(f'''
      The following is the structuring from a transcript of a conversation that just finished.
      First determine if there's crucial feedback to notify a busy entrepreneur about it.
      If not, simply output an empty string, but if it is important, output 20 words (at most) with the most important feedback for the conversation.
      Be short, concise, and helpful, and specially strict on determining if it's worth notifying or not.
       
      Transcript:
      ${memory.transcript}
      
      Structured version:
      ${memory.structured.dict()}
    ''')
    return {'message': '' if len(response.content) < 5 else response.content}
