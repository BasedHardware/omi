from fastapi import APIRouter
from langchain_community.tools.asknews import AskNewsSearch
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

from db import clean_all_transcripts_except, append_segment_to_transcript, remove_transcript
from models import TranscriptSegment, RealtimePluginRequest, EndpointResponse

router = APIRouter()
chat = ChatOpenAI(model='gpt-4o', temperature=0)


# chat = ChatGroq(
#     temperature=0,
#     model="llama-3.1-70b-versatile",
#     # model='llama3-groq-8b-8192-tool-use-preview',
# )


class NewsCheck(BaseModel):
    query: str = Field(description="The query to ask a news search engine, can be empty.", default='')


def news_checker(conversation: list[dict]) -> str:
    # TODO: use chains instead
    chat_with_parser = chat.with_structured_output(NewsCheck)
    conversation_str = TranscriptSegment.segments_as_string(conversation)
    print(conversation_str)
    result: NewsCheck = chat_with_parser.invoke(f'''
    You will be given a segment of an ongoing conversation.

    Your task is to determine if the conversation specifically discusses facts that appear conspiratorial, unscientific, or super biased.
    Only if the topic is of significant importance and urgency for the user to be aware of, provide a question to be asked to a news search engine, in order to debunk the conversation in process.
    Otherwise, output an empty question.

    Transcript:
    {conversation_str}
    ''')
    print('News Query:', result.query)
    if len(result.query) < 5:
        return ''

    tool = AskNewsSearch(max_results=2)
    output = tool.invoke({"query": result.query})
    result = chat.invoke(f'''
    A user just asked a search engine news the following question:
    {result.query}

    The output was: {output}

    The conversation is:
    {conversation_str}

    Your task is to provide a 15 words summary to help debunk and contradict the obvious bias and conspiranoic conversation going. If you don't find anything like this, just output an empty string.
    ''')
    print('Output', result.content)
    if len(result.content) < 5:
        return ''
    return result.content


@router.post('/news-checker', tags=['advanced', 'realtime'], response_model=EndpointResponse)
def news_checker_endpoint(uid: str, data: RealtimePluginRequest):
    clean_all_transcripts_except(uid, data.session_id)
    transcript: list[dict] = append_segment_to_transcript(uid, data.session_id, data.get_segments())
    message = news_checker(transcript)

    if message:
        # so that in the next call with already triggered stuff, it doesn't trigger again
        remove_transcript(uid, data.session_id)

    return {'message': message}
