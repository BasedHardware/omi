from typing import List

from fastapi import APIRouter
from langchain_community.tools.asknews import AskNewsSearch
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from db import clean_all_transcripts_except, append_segment_to_transcript, remove_transcript
from models import RealtimePluginRequest, EndpointResponse, TranscriptSegment

router = APIRouter()
chat = ChatOpenAI(model='gpt-4o', temperature=0)

chat_groq_8b = ChatGroq(
    temperature=0,
    # model="llama-3.1-70b-versatile",
    model="llama3-70b-8192",
    # model='llama3-groq-8b-8192-tool-use-preview',
)


class NewsCheck(BaseModel):
    query: str = Field(description="The query to ask a news search engine, can be empty.", default='')


def news_checker(conversation: List[TranscriptSegment]) -> str:
    chat_with_parser = chat_groq_8b.with_structured_output(NewsCheck)
    conversation_str = TranscriptSegment.segments_as_string(conversation)
    result: NewsCheck = chat_with_parser.invoke(f'''
    You will be given the last few transcript words of an ongoing conversation.

    Your task is to determine if the conversation specifically discusses facts that appear conspiratorial, unscientific, or super biased.
    Historic events, that seem to contradict logic and common sense should also be considered.
    Only if the topic is of significant importance and urgency for the user to be aware of, provide a question to be asked to a news search engine, in order to debunk the conversation in process.
    Otherwise, output an empty question.

    Transcript:
    {conversation_str}
    ''')
    if len(result.query) < 5:
        return ''

    print('news_checker query:', result.query)
    tool = AskNewsSearch(max_results=2)
    output = tool.invoke({"query": result.query})
    result = chat_groq_8b.invoke(f'''
    A user just asked a search engine news the following question:
    {result.query}

    The output was: {output}

    The conversation is:
    {conversation_str}

    Your task is to provide a 15 words summary to help debunk and contradict the obvious bias and conspiranoic conversation going. If you don't find anything like this, just output an empty string.
    ''')
    if len(result.content) < 5:
        return ''
    print('news_checker output:', result.content)
    return result.content


@router.post('/news-checker', tags=['advanced', 'realtime'], response_model=EndpointResponse)
def news_checker_endpoint(uid: str, data: RealtimePluginRequest):
    # return {'message': ''}
    print('news_checker_endpoint', uid)
    session_id = 'news-checker-' + data.session_id
    clean_all_transcripts_except(uid, session_id)
    transcript: List[TranscriptSegment] = append_segment_to_transcript(uid, session_id, data.segments)
    message = news_checker(transcript)

    if message:
        # so that in the next call with already triggered stuff, it doesn't trigger again
        remove_transcript(uid, session_id)

    return {'message': message}


class EmotionalSupport(BaseModel):
    message: str = Field(description='The message that will be sent to the user, can be empty.', default='')


def emotional_support(segments: list[TranscriptSegment]) -> str:
    chat_with_parser = chat_groq_8b.with_structured_output(EmotionalSupport)
    result: EmotionalSupport = chat_with_parser.invoke(f'''
    You will be given a segment of an ongoing conversation.
    Your task is to detect if there are any accentuated emotions on the conversation and act if it's something unpleasant.
    Please make sure that there's something valueable to say that will improve user's mood, otherwise output an empty string.
    The user is super busy and needs to be as productive as possible, so only output something if it's really worth it.
    
    Transcript:
    {TranscriptSegment.segments_as_string(segments)}
    
    The message has to be at most 20 words. Be short and concise.
    ''')

    print('emotional_support output:', result.message)
    if len(result.message) < 10:
        return ''
    return result.message


@router.post('/emotional-support', tags=['advanced', 'realtime'], response_model=EndpointResponse)
def emotional_support_plugin(uid: str, data: RealtimePluginRequest):
    # return {'message': ''}
    session_id = 'emotional-support-' + data.session_id
    clean_all_transcripts_except(uid, session_id)
    transcript: List[TranscriptSegment] = append_segment_to_transcript(uid, session_id, data.segments)
    message = emotional_support(transcript)

    if message:
        # so that in the next call with already triggered stuff, it doesn't trigger again
        remove_transcript(uid, session_id)

    return {'message': message}
