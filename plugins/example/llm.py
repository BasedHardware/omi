from typing import List, Dict

from langchain_community.tools.asknews import AskNewsSearch
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI

from models import Memory

chat = ChatOpenAI(model='gpt-4o', temperature=0)


# chat = ChatGroq(
#     temperature=0,
#     model="llama-3.1-70b-versatile",
#     # model='llama3-groq-8b-8192-tool-use-preview',
# )

class BooksToBuy(BaseModel):
    books: List[str] = Field(description="The list of titles of the books to buy", default=[], min_items=0)


class NewsCheck(BaseModel):
    query: str = Field(description="The query to ask a news search engine, can be empty.", default='')


def retrieve_books_to_buy(memory: Memory) -> List[str]:
    # has_user_set = any(filter(lambda x: x.is_user, memory.transcriptSegments))

    chat_with_parser = chat.with_structured_output(BooksToBuy)
    response: BooksToBuy = chat_with_parser.invoke(f'''
    The following is the transcript of a conversation.
    {memory.transcript}
    
    Your task is to determine is first to determine if the speakers talked about a book or suggested, recommended books to each other \
    at some point during the conversation, and provide the titles of those.
    ''')
    print('Books to buy:', response.books)
    return response.books


def get_timestamp_string(start: float, end: float) -> str:
    def format_duration(seconds: float) -> str:
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        remaining_seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{remaining_seconds:02}"

    start_str = format_duration(start)
    end_str = format_duration(end)

    return f"{start_str} - {end_str}"


def segments_as_string(segments: List[Dict]) -> str:
    transcript = ''

    for segment in segments:
        segment_text = segment['text'].strip()
        timestamp_str = f"[{get_timestamp_string(segment['start'], segment['end'])}]"
        if segment.get('is_user', False):
            transcript += f"{timestamp_str} User: {segment_text} "
        else:
            transcript += f"{timestamp_str} Speaker {segment.get('speaker_id', '')}: {segment_text} "
        transcript += '\n\n'

    return transcript.strip()


def news_checker(conversation: list[dict]) -> str:
    # TODO: use chains instead
    chat_with_parser = chat.with_structured_output(NewsCheck)
    conversation_str = segments_as_string(conversation)
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
