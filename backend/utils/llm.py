### Note: Currently, response_time is hardcoded as a placeholder (0.5). In production, you might consider actually measuring the time taken to generate responses.

import json
import re
import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict

import tiktoken
import redis
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field, ValidationError

from database.redis_db import add_filter_category_item
from models.app import App
from models.chat import Message, MessageSender
from models.facts import Fact, FactCategory
from models.memory import Structured, MemoryPhoto, CategoryEnum, Memory
from models.plugin import Plugin
from models.transcript_segment import TranscriptSegment
from models.trend import TrendEnum, ceo_options, company_options, software_product_options, hardware_product_options, ai_product_options, TrendType
from utils.memories.facts import get_prompt_facts
from utils.prompts import extract_facts_prompt, extract_learnings_prompt

# Initialize LLM and embeddings
llm_mini = ChatOpenAI(model='gpt-4o-mini')
llm_mini_stream = ChatOpenAI(model='gpt-4o-mini', streaming=True)
llm_large = ChatOpenAI(model='o1-preview')
llm_large_stream = ChatOpenAI(model='o1-preview', streaming=True, temperature=1)
llm_medium = ChatOpenAI(model='gpt-4o')
llm_medium_stream = ChatOpenAI(model='gpt-4o', streaming=True)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
parser = PydanticOutputParser(pydantic_object=Structured)

# Redis client for persistence (assumes Redis running locally; adjust host/port as needed)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

encoding = tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


# **********************************************
# ************* MEMORY PROCESSING **************
# **********************************************

class DiscardMemory(BaseModel):
    discard: bool = Field(description="If the memory should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def should_discard_memory(transcript: str) -> bool:
    if len(transcript.split(' ')) > 100:
        return False

    parser_local = PydanticOutputParser(pydantic_object=DiscardMemory)
    prompt = ChatPromptTemplate.from_messages([
        '''
        You will be given a conversation transcript, and your task is to determine if the conversation is worth storing as a memory or not.
        It is not worth storing if there are no interesting topics, facts, or information, in that case, output discard = True.

        Transcript: ```{transcript}```

        {format_instructions}'''.replace('    ', '').strip()
    ])
    chain = prompt | llm_mini | parser_local
    try:
        response: DiscardMemory = chain.invoke({
            'transcript': transcript.strip(),
            'format_instructions': parser_local.get_format_instructions(),
        })
        return response.discard
    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return False


def get_transcript_structure(transcript: str, started_at: datetime, language_code: str, tz: str) -> Structured:
    prompt = ChatPromptTemplate.from_messages([(
        'system',
        '''You are an expert conversation analyzer. Your task is to analyze the conversation and provide structure and clarity to the recording transcription of a conversation.
        The conversation language is {language_code}. Use the same language {language_code} for your response.

        For the title, use the main topic of the conversation.
        For the overview, condense the conversation into a summary with the main topics discussed, make sure to capture the key points and important details from the conversation.
        For the action items, include a list of commitments, specific tasks or actionable steps from the conversation that the user is planning to do or has to do on that specific day or in future. Remember the speaker is busy so this has to be very efficient and concise, otherwise they might miss some critical tasks. Specify which speaker is responsible for each action item.
        For the category, classify the conversation into one of the available categories.
        For Calendar Events, include a list of events extracted from the conversation, that the user must have on his calendar. For date context, this conversation happened on {started_at}. {tz} is the user's timezone, convert it to UTC and respond in UTC.

        Transcript: ```{transcript}```

        {format_instructions}'''.replace('    ', '').strip()
    )])
    chain = prompt | ChatOpenAI(model='gpt-4o') | parser

    response = chain.invoke({
        'transcript': transcript.strip(),
        'format_instructions': parser.get_format_instructions(),
        'language_code': language_code,
        'started_at': started_at.isoformat(),
        'tz': tz,
    })

    for event in (response.events or []):
        if event.duration > 180:
            event.duration = 180
        event.created = False
    return response


def get_plugin_result(transcript: str, plugin: Plugin) -> str:
    prompt = f'''
    Your are an AI with the following characteristics:
    Name: ${plugin.name},
    Description: ${plugin.description},
    Task: ${plugin.memory_prompt}

    Note: It is possible that the conversation you are given, has nothing to do with your task, \
    in that case, output an empty string. (For example, you are given a business conversation, but your task is medical analysis)

    Conversation: ```{transcript.strip()}```,

    Make sure to be concise and clear.
    '''
    response = llm_mini.invoke(prompt)
    content = response.content.replace('```json', '').replace('```', '')
    if len(content) < 5:
        return ''
    return content


# **************************************
# ************* OPENGLASS **************
# **************************************

def summarize_open_glass(photos: List[MemoryPhoto]) -> Structured:
    photos_str = ''
    for i, photo in enumerate(photos):
        photos_str += f'{i + 1}. "{photo.description}"\n'
    prompt = f'''The user took a series of pictures from his POV, generated a description for each photo, and wants to create a memory from them.

      For the title, use the main topic of the scenes.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.

      Photos Descriptions: ```{photos_str}```
      '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(Structured).invoke(prompt)


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************

def summarize_experience_text(text: str) -> Structured:
    prompt = f'''The user sent a text of their own experiences or thoughts, and wants to create a memory from it.

      For the title, use the main topic of the experience or thought.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.

      Text: ```{text}```
      '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(Structured).invoke(prompt)


def get_memory_summary(uid: str, memories: List[Memory]) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    conversation_history = Memory.memories_to_string(memories)

    prompt = f"""
    You are an experienced mentor, that helps people achieve their goals and improve their lives.
    You are advising {user_name} right now, {facts_str}

    The following are a list of {user_name}'s conversations from today, with the transcripts and a slight summary of each, that {user_name} had during his day.
    {user_name} wants to get a summary of the key action items {user_name} has to take based on today's conversations.

    Remember {user_name} is busy so this has to be very efficient and concise.
    Respond in at most 50 words.

    Output your response in plain text, without markdown. No newline character and only use numbers for the action items.
${conversation_history}

text

Collapse

Wrap

Copy
    """.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]


# ****************************************
# ************* CHAT BASICS **************
# ****************************************

def initial_chat_message(uid: str, plugin: Optional[App] = None, prev_messages_str: str = '') -> str:
    user_name, facts_str = get_prompt_facts(uid)
    if plugin is None:
        prompt = f"""
You are 'Friend', a friendly and helpful assistant who aims to make {user_name}'s life better 10x.
You know the following about {user_name}: {facts_str}.

{prev_messages_str}

Compose {"an initial" if not prev_messages_str else "a follow-up"} message to {user_name} that fully embodies your friendly and helpful personality. Use warm and cheerful language, and include light humor if appropriate. The message should be short, engaging, and make {user_name} feel welcome. Do not mention that you are an assistant or that this is an initial message; just {"start" if not prev_messages_str else "continue"} the conversation naturally, showcasing your personality.
"""
    else:
        prompt = f"""
You are '{plugin.name}', {plugin.chat_prompt}.
You know the following about {user_name}: {facts_str}.

{prev_messages_str}

As {plugin.name}, fully embrace your personality and characteristics in your {"initial" if not prev_messages_str else "follow-up"} message to {user_name}. Use language, tone, and style that reflect your unique personality traits. {"Start" if not prev_messages_str else "Continue"} the conversation naturally with a short, engaging message that showcases your personality and humor, and connects with {user_name}. Do not mention that you are an AI or that this is an initial message.
"""
    prompt = prompt.strip()
    return llm_mini.invoke(prompt).content


def _get_answer_simple_message_prompt(uid: str, messages: List[Message], plugin: Optional[Plugin] = None) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )
    user_name, facts_str = get_prompt_facts(uid)

    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    return f"""
You are an assistant for engaging personal conversations.
You are made for {user_name}, {facts_str}

Use what you know about {user_name}, to continue the conversation, feel free to ask questions, share stories, or just say hi.
{plugin_info}

Conversation History:
{conversation_history}

Answer:
""".replace('    ', '').strip()


def answer_simple_message(uid: str, messages: List[Message], plugin: Optional[Plugin] = None) -> str:
    prompt = _get_answer_simple_message_prompt(uid, messages, plugin)
    return llm_mini.invoke(prompt).content


def answer_simple_message_stream(uid: str, messages: List[Message], plugin: Optional[Plugin] = None, callbacks=[]) -> str:
    prompt = _get_answer_simple_message_prompt(uid, messages, plugin)
    return llm_mini_stream.invoke(prompt, {'callbacks': callbacks}).content


def _get_answer_omi_question_prompt(messages: List[Message], context: str) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )
    return f"""
You are an assistant for answering questions about the app Omi, also known as Friend.
Continue the conversation, answering the question based on the context provided.

Context:
{context}

text

Collapse

Wrap

Copy

Conversation History:
{conversation_history}

Answer:
""".replace('    ', '').strip()


def answer_omi_question(messages: List[Message], context: str) -> str:
    prompt = _get_answer_omi_question_prompt(messages, context)
    return llm_mini.invoke(prompt).content


def answer_omi_question_stream(messages: List[Message], context: str, callbacks: []) -> str:
    prompt = _get_answer_omi_question_prompt(messages, context)
    return llm_mini_stream.invoke(prompt, {'callbacks': callbacks}).content


# Updated QA prompt function with markdown and data-driven instructions
def _get_qa_rag_prompt(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False,
                       messages: List[Message] = [], tz: Optional[str] = "UTC") -> str:
    user_name, facts_str = get_prompt_facts(uid)
    facts_str = '\n'.join(facts_str.split('\n')[1:]).strip()

    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    cited_instruction = """
- You MUST cite the most relevant <memories> that answer the question. \
  - Only cite in <memories> not <user_facts>, not <previous_messages>.
  - Cite in memories using [index] at the end of sentences when needed, for example "You discussed optimizing firmware with your teammate yesterday[1][2]".
  - NO SPACE between the last word and the citation.
  - Avoid citing irrelevant memories.
"""

    return f"""
<assistant_role>
    You are an assistant for question-answering tasks.
</assistant_role>

<task>
    Write an accurate, detailed, and comprehensive response to the <question> in the most personalized way possible, using the <memories>, <user_facts> provided.
</task>

<instructions>
- Refine the <question> based on the last <previous_messages> before answering it.
- DO NOT use the AI's message from <previous_messages> as references to answer the <question>.
- Use <question_timezone> and <current_datetime_utc> to refer to the time context of the <question>.
- It is EXTREMELY IMPORTANT to directly answer the question, keep the answer concise and high-quality.
- Use markdown (e.g., **bold**, *italic*, or lists) to enhance readability where appropriate.
- Leverage <user_facts> and <memories> to tailor the response specifically to the user.
- If you don't know the answer or the premise is incorrect, explain why. If the <memories> are empty or unhelpful, answer the question as well as you can with existing knowledge.
- You MUST follow the <reports_instructions> if the user is asking for reporting or summarizing their dates, weeks, months, or years.
{cited_instruction if cited and len(context) > 0 else ""}
{"- Regard the <plugin_instructions>" if len(plugin_info) > 0 else ""}.
</instructions>

<plugin_instructions>
{plugin_info}
</plugin_instructions>

<reports_instructions>
- Answer with the template:
 - **Goals and Achievements**
 - **Mood Tracker**
 - **Gratitude Log**
 - **Lessons Learned**
</reports_instructions>

<question>
{question}
</question>

<memories>
{context}
</memories>

<previous_messages>
{Message.get_messages_as_xml(messages)}
</previous_messages>

<user_facts>
[Use the following User Facts if relevant to the <question>]
    {facts_str.strip()}
</user_facts>

<current_datetime_utc>
    Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
</current_datetime_utc>

<question_timezone>
    Question's timezone: {tz}
</question_timezone>

<answer>
""".replace('    ', '').replace('\n\n\n', '\n\n').strip()


def qa_rag(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False,
           messages: List[Message] = [], tz: Optional[str] = "UTC") -> str:
    prompt = _get_qa_rag_prompt(uid, question, context, plugin, cited, messages, tz)
    return llm_medium.invoke(prompt).content


def qa_rag_stream(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False,
                  messages: List[Message] = [], tz: Optional[str] = "UTC", callbacks=[]) -> str:
    prompt = _get_qa_rag_prompt(uid, question, context, plugin, cited, messages, tz)
    return llm_medium_stream.invoke(prompt, {'callbacks': callbacks}).content


# *********************************************
# ************* RETRIEVAL + CHAT **************
# *********************************************

class RequiresContext(BaseModel):
    value: bool = Field(description="Based on the conversation, this tells if context is needed to respond")


class TopicsContext(BaseModel):
    topics: List[CategoryEnum] = Field(default=[], description="List of topics.")


class DatesContext(BaseModel):
    dates_range: List[datetime] = Field(
        default=[],
        examples=[['2024-12-23T00:00:00+07:00', '2024-12-23T23:59:00+07:00']],
        description="Dates range. (Optional)",
    )


def requires_context_v1(messages: List[Message]) -> bool:
    prompt = f'''
Based on the current conversation your task is to determine whether the user is asking a question or a follow up question that requires context outside the conversation to be answered.
Take as example: if the user is saying "Hi", "Hello", "How are you?", "Good morning", etc, the answer is False.

Conversation History:
{Message.get_messages_as_string(messages)}
'''
    with_parser = llm_mini.with_structured_output(RequiresContext)
    response: RequiresContext = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


def requires_context(question: str) -> bool:
    prompt = f'''
Based on the current question your task is to determine whether the user is asking a question that requires context outside the conversation to be answered.
Take as example: if the user is saying "Hi", "Hello", "How are you?", "Good morning", etc, the answer is False.

User's Question:
{question}
'''
    with_parser = llm_mini.with_structured_output(RequiresContext)
    response: RequiresContext = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


class IsAnOmiQuestion(BaseModel):
    value: bool = Field(description="If the message is an Omi/Friend related question")


def retrieve_is_an_omi_question_v1(messages: List[Message]) -> bool:
    prompt = f'''
The user is using the chat functionality of an app known as Omi or Friend.
Based on the current conversation your task is to determine if the user is asking a question about the way you work, or how to use you or the app.

Questions like,
- "How does it work?"
- "What can you do?"
- "How can I buy it"
- "Where do I get it"
- "How the chat works?"
- ...

Conversation History:
{Message.get_messages_as_string(messages)}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(IsAnOmiQuestion)
    response: IsAnOmiQuestion = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


def retrieve_is_an_omi_question_v2(messages: List[Message]) -> bool:
    prompt = f'''
Task: Analyze the conversation to identify if the user is inquiring about the functionalities or usage of the app, Omi or Friend. Focus on detecting questions related to the app's operations or capabilities.

Examples of User Questions:

- "How does it work?"
- "What can you do?"
- "How can I buy it?"
- "Where do I get it?"
- "How does the chat function?"

Instructions:

1. Review the conversation history carefully.
2. Determine if the user is asking about:
 - The operational aspects of the app.
 - How to utilize the app effectively.
 - Any specific features or purchasing options.

Output: Clearly state if the user is asking a question related to the app's functionality or usage. If yes, specify the nature of the inquiry.

Conversation Context:
{Message.get_messages_as_string(messages)}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(IsAnOmiQuestion)
    response: IsAnOmiQuestion = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


def retrieve_is_an_omi_question(question: str) -> bool:
    prompt = f'''
Task: Analyze the question to identify if the user is inquiring about the functionalities or usage of the app, Omi or Friend. Focus on detecting questions related to the app's operations or capabilities.

Examples of User Questions:

- "How does it work?"
- "What can you do?"
- "How can I buy it?"
- "Where do I get it?"
- "How does the chat function?"

Instructions:

1. Review the question carefully.
2. Determine if the user is asking about:
 - The operational aspects of the app.
 - How to utilize the app effectively.
 - Any specific features or purchasing options.

Output: Clearly state if the user is asking a question related to the app's functionality or usage. If yes, specify the nature of the inquiry.

User's Question:
{question}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(IsAnOmiQuestion)
    response: IsAnOmiQuestion = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


class IsFileQuestion(BaseModel):
    value: bool = Field(description="If the message is related to file/image")


def retrieve_is_file_question(question: str) -> bool:
    prompt = f'''
Based on the current question, your task is to determine whether the user is referring to a file or an image that was just attached or mentioned earlier in the conversation.

Examples where the answer is True:
- "Can you process this file?"
- "What do you think about the image I uploaded?"
- "Can you extract text from the document?"

Examples where the answer is False:
- "How is the weather today?"
- "Tell me a joke."
- "What is the capital of France?"

User's Question:
{question}
'''
    with_parser = llm_mini.with_structured_output(IsFileQuestion)
    response: IsFileQuestion = with_parser.invoke(prompt)
    try:
        return response.value
    except ValidationError:
        return False


def retrieve_context_topics(messages: List[Message]) -> List[str]:
    prompt = f'''
Based on the current conversation an AI and a User are having, for the AI to answer the latest user messages, it needs context outside the conversation.

Your task is to extract the correct and most accurate context in the conversation, to be used to retrieve more information.
Provide a list of topics in which the current conversation needs context about, in order to answer the most recent user request.

It is possible that the data needed is not related to a topic, in that case, output an empty list.

Conversation:
{Message.get_messages_as_string(messages)}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(TopicsContext)
    try:
        response: TopicsContext = with_parser.invoke(prompt)
        topics = list(map(lambda x: str(x.value).capitalize(), response.topics))
    except ValidationError:
        topics = [CategoryEnum.other.value.capitalize()]
    return topics


def retrieve_context_dates(messages: List[Message], tz: str) -> List[datetime]:
    prompt = f'''
Based on the current conversation an AI and a User are having, for the AI to answer the latest user messages, it needs context outside the conversation.

Your task is to find the dates range in which the current conversation needs context about, in order to answer the most recent user request.

For example, if the user request relates to "What did I do last week?", or "What did I learn yesterday", or "Who did I meet today?", the dates range should be provided.
Other type of dates, like historical events, or future events, should be ignored and an empty list should be returned.

For context, today is {datetime.now(timezone.utc).strftime('%Y-%m-%d')} in UTC. {tz} is the user's timezone, convert it to UTC and respond in UTC.

Conversation:
{Message.get_messages_as_string(messages)}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range


def retrieve_context_dates_by_question(question: str, tz: str) -> List[datetime]:
    prompt = f'''
You MUST determine the appropriate date range in {tz} that provides context for answering the <question> provided.

If the <question> does not reference a date or a date range, respond with an empty list: []

Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

<question>
{question}
</question>
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range


def chunk_extraction(segments: List[TranscriptSegment], topics: List[str]) -> str:
    content = TranscriptSegment.segments_as_string(segments)
    prompt = f'''
You are an experienced detective, your task is to extract the key points of the conversation related to the topics you were provided.
You will be given a conversation transcript of a low quality recording, and a list of topics.

Include the most relevant information about the topics, people mentioned, events, locations, facts, phrases, and any other relevant information.
It is possible that the conversation doesn't have anything related to the topics, in that case, output an empty string.

Conversation:
{content}

Topics: {topics}
'''
    # Note: SummaryOutput is assumed to be a defined Pydantic model with a 'summary' field.
    with_parser = llm_mini.with_structured_output(SummaryOutput)
    response: SummaryOutput = with_parser.invoke(prompt)
    return response.summary


# **************************************************
# ************* RETRIEVAL (EMOTIONAL) **************
# **************************************************

def retrieve_memory_context_params(memory: Memory) -> List[str]:
    transcript = memory.get_transcript(False)
    if len(transcript) == 0:
        return []

    prompt = f'''
Based on the current transcript of a conversation.

Your task is to extract the correct and most accurate context in the conversation, to be used to retrieve more information.
Provide a list of topics in which the current conversation needs context about, in order to answer the most recent user request.

Conversation:
{transcript}
'''.replace('    ', '').strip()

    try:
        with_parser = llm_mini.with_structured_output(TopicsContext)
        response: TopicsContext = with_parser.invoke(prompt)
        return response.topics
    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return []


def obtain_emotional_message(uid: str, memory: Memory, context: str, emotion: str) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    transcript = memory.get_transcript(False)
    prompt = f"""
You are a thoughtful and encouraging Friend.
Your best friend is {user_name}, {facts_str}

{user_name} just finished a conversation where {user_name} experienced {emotion}.

You will be given the conversation transcript, and context from previous related conversations of {user_name}.

Remember, {user_name} is feeling {emotion}.
Use what you know about {user_name}, the transcript, and the related context, to help {user_name} overcome this feeling \
(if bad), or celebrate (if good), by giving advice, encouragement, support, or suggesting the best action to take.

Make sure the message is nice and short, no more than 20 words.

Conversation Transcript:
{transcript}

Context:
{context}

text

Collapse

Wrap

Copy
""".replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


# **********************************
# ************* FACTS **************
# **********************************

class Facts(BaseModel):
    facts: List[Fact] = Field(
        min_items=0,
        max_items=3,
        description="List of **new** facts. If any",
        default=[],
    )


def new_facts_extractor(
    uid: str, segments: List[TranscriptSegment], user_name: Optional[str] = None, facts_str: Optional[str] = None
) -> List[Fact]:
    if user_name is None or facts_str is None:
        user_name, facts_str = get_prompt_facts(uid)

    content = TranscriptSegment.segments_as_string(segments, user_name=user_name)
    if not content or len(content) < 25:
        return []

    try:
        parser_local = PydanticOutputParser(pydantic_object=Facts)
        chain = extract_facts_prompt | llm_mini | parser_local
        response: Facts = chain.invoke({
            'user_name': user_name,
            'conversation': content,
            'facts_str': facts_str,
            'format_instructions': parser_local.get_format_instructions(),
        })
        return response.facts
    except Exception as e:
        print(f'Error extracting new facts: {e}')
        return []


class Learnings(BaseModel):
    result: List[str] = Field(
        min_items=0,
        max_items=2,
        description="List of **new** learnings. If any",
        default=[],
    )


def new_learnings_extractor(
    uid: str, segments: List[TranscriptSegment], user_name: Optional[str] = None,
    learnings_str: Optional[str] = None
) -> List[Fact]:
    if user_name is None or learnings_str is None:
        user_name, facts_str = get_prompt_facts(uid)

    content = TranscriptSegment.segments_as_string(segments, user_name=user_name)
    if not content or len(content) < 100:
        return []

    try:
        parser_local = PydanticOutputParser(pydantic_object=Learnings)
        chain = extract_learnings_prompt | llm_mini | parser_local
        response: Learnings = chain.invoke({
            'user_name': user_name,
            'conversation': content,
            'learnings_str': learnings_str,
            'format_instructions': parser_local.get_format_instructions(),
        })
        return list(map(lambda x: Fact(content=x, category=FactCategory.learnings), response.result))
    except Exception as e:
        print(f'Error extracting new facts: {e}')
        return []


# **********************************
# ************* TRENDS **************
# **********************************

class Item(BaseModel):
    category: TrendEnum = Field(description="The category identified")
    type: TrendType = Field(description="The sentiment identified")
    topic: str = Field(description="The specific topic corresponding the category")


class ExpectedOutput(BaseModel):
    items: List[Item] = Field(default=[], description="List of items.")


def trends_extractor(memory: Memory) -> List[Item]:
    transcript = memory.get_transcript(False)
    if len(transcript) == 0:
        return []

    prompt = f'''
You will be given a finished conversation transcript.
You are responsible for extracting the topics of the conversation and classifying each one within one the following categories: {str([e.value for e in TrendEnum]).strip("[]")}.
You must identify if the perception is positive or negative, and classify it as "best" or "worst".

For the specific topics here are the options available, you must classify the topic within one of these options:
- ceo_options: {", ".join(ceo_options)}
- company_options: {", ".join(company_options)}
- software_product_options: {", ".join(software_product_options)}
- hardware_product_options: {", ".join(hardware_product_options)}
- ai_product_options: {", ".join(ai_product_options)}

For example,
If you identify the topic "Tesla stock has been going up incredibly", you should output:
- Category: company
- Type: best
- Topic: Tesla

Conversation:
{transcript}
'''.replace('    ', '').strip()
    try:
        with_parser = llm_mini.with_structured_output(ExpectedOutput)
        response: ExpectedOutput = with_parser.invoke(prompt)
        filtered = []
        for item in response.items:
            if item.topic not in [e for e in (ceo_options + company_options + software_product_options + hardware_product_options + ai_product_options)]:
                continue
            filtered.append(item)
        return filtered
    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return []


# **********************************************************
# ************* RANDOM JOAN SPECIFIC FEATURES **************
# **********************************************************

def followup_question_prompt(segments: List[TranscriptSegment]):
    transcript_str = TranscriptSegment.segments_as_string(segments, include_timestamps=False)
    words = transcript_str.split()
    w_count = len(words)
    if w_count < 10:
        return ''
    elif w_count > 100:
        transcript_str = ' '.join(words[-100:])

    prompt = f"""
    You will be given the transcript of an in-progress conversation.
    Your task as an engaging, fun, and curious conversationalist, is to suggest the next follow-up question to keep the conversation engaging.

    Conversation Transcript:
    {transcript_str}

    Output your response in plain text, without markdown.
    Output only the question, without context, be concise and straight to the point.
    """.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


# **********************************************
# ************* CHAT V2 LANGGRAPH **************
# **********************************************

class ExtractedInformation(BaseModel):
    people: List[str] = Field(
        default=[],
        examples=[['John Doe', 'Jane Doe']],
        description='Identify all the people names who were mentioned during the conversation.'
    )
    topics: List[str] = Field(
        default=[],
        examples=[['Artificial Intelligence', 'Machine Learning']],
        description='List all the main topics and subtopics that were discussed.',
    )
    entities: List[str] = Field(
        default=[],
        examples=[['OpenAI', 'GPT-4']],
        description='List any products, technologies, places, or other entities that are relevant to the conversation.'
    )
    dates: List[str] = Field(
        default=[],
        examples=[['2024-01-01', '2024-01-02']],
        description=f'Extract any dates mentioned in the conversation. Use the format YYYY-MM-DD.'
    )


class FiltersToUse(BaseModel):
    people: List[str] = Field(default=[], description='People, names that could be relevant')
    topics: List[str] = Field(default=[], description='Topics and subtopics that can help finding more information')
    entities: List[str] = Field(
        default=[], description='products, technologies, places, or other entities that could be relevant.'
    )


class OutputQuestion(BaseModel):
    question: str = Field(description='The extracted user question from the conversation.')


def extract_question_from_conversation(messages: List[Message]) -> str:
    user_message_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].sender == MessageSender.ai:
            break
        if messages[i].sender == MessageSender.human:
            user_message_idx = i
    user_last_messages = messages[user_message_idx:]
    if len(user_last_messages) == 0:
        return ""

    prompt = f'''
You will be given a recent conversation between a <user> and an <AI>. \
The conversation may include a few messages exchanged in <previous_messages> and partly build up the proper question. \
Your task is to understand the <user_last_messages> and identify the question or follow-up question the user is asking.

You will be provided with <previous_messages> between you and the user to help you indentify the question.

First, determine whether the user is asking a question or a follow-up question. \
If the user is not asking a question or does not want to follow up, respond with an empty message. \
For example, if the user says "Hi", "Hello", "How are you?", or "Good morning", the answer should be empty.

If the <user_last_messages> contain a complete question, maintain the original version as accurately as possible. \
Avoid adding unnecessary words.

You MUST keep the original <date_in_term>

Output a WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

<user_last_messages>
{Message.get_messages_as_xml(user_last_messages)}
</user_last_messages>

<previous_messages>
{Message.get_messages_as_xml(messages)}
</previous_messages>

<date_in_term>
- today
- my day
- my week
- this week
- this day
- etc.
</date_in_term>
'''.replace('    ', '').strip()
    question = llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question
    return question


def retrieve_metadata_fields_from_transcript(
    uid: str, created_at: datetime, transcript_segment: List[dict], tz: str
) -> ExtractedInformation:
    transcript = ''
    for segment in transcript_segment:
        transcript += f'{segment["text"].strip()}\n\n'

    prompt = f'''
You will be given the raw transcript of a conversation, this transcript has about 20% word error rate,
and diarization is also made very poorly.

Your task is to extract the most accurate information from the conversation in the output object indicated below.

Make sure as a first step, you infer and fix the raw transcript errors and then proceed to extract the information.

For context when extracting dates, today is {created_at.astimezone(timezone.utc).strftime('%Y-%m-%d')} in UTC. {tz} is the user's timezone, convert it to UTC and respond in UTC.
If one says "today", it means the current day.
If one says "tomorrow", it means the next day after today.
If one says "yesterday", it means the day before today.
If one says "next week", it means the next monday.
Do not include dates greater than 2025.

Conversation Transcript:
{transcript}

text

Collapse

Wrap

Copy
'''.replace('    ', '')
    try:
        result: ExtractedInformation = llm_mini.with_structured_output(ExtractedInformation).invoke(prompt)
    except Exception as e:
        print('e', e)
        return ExtractedInformation(people=[], topics=[], entities=[], dates=[])

    def normalize_filter(value: str) -> str:
        value = value.lower().strip()
        value = re.sub(r'[^\w\s-]', '', value)
        value = re.sub(r'\s+', ' ', value)
        filler_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to'}
        value = ' '.join(word for word in value.split() if word not in filler_words)
        value = value.replace('artificial intelligence', 'ai').replace('machine learning', 'ml').replace('natural language processing', 'nlp')
        return value.strip()

    metadata = {
        'people': [normalize_filter(p) for p in result.people],
        'topics': [normalize_filter(t) for t in result.topics],
        'entities': [normalize_filter(e) for e in result.entities],
        'dates': []
    }
    for date in result.dates:
        try:
            parsed_date = datetime.strptime(date, '%Y-%m-%d')
            if parsed_date.year > 2025:
                continue
            metadata['dates'].append(parsed_date.strftime('%Y-%m-%d'))
        except Exception as e:
            print(f'Error parsing date: {e}')

    for p in metadata['people']:
        add_filter_category_item(uid, 'people', p)
    for t in metadata['topics']:
        add_filter_category_item(uid, 'topics', t)
    for e in metadata['entities']:
        add_filter_category_item(uid, 'entities', e)
    for d in metadata['dates']:
        add_filter_category_item(uid, 'dates', d)

    return result


def select_structured_filters(question: str, filters_available: dict) -> dict:
    prompt = f'''
Based on a question asked by the user to an AI, the AI needs to search for the user information related to topics, entities, people, and dates that will help it answering.
Your task is to identify the correct fields that can be related to the question and can help answering.

You must choose for each field, only the ones available in the JSON below.
Find as many as possible that can relate to the question asked.
{json.dumps(filters_available, indent=2)}

text

Collapse

Wrap

Copy

Question: {question}
'''.replace('    ', '').strip()
    with_parser = llm_mini.with_structured_output(FiltersToUse)
    try:
        response: FiltersToUse = with_parser.invoke(prompt)
        response.topics = [t for t in response.topics if t in filters_available['topics']]
        response.people = [p for p in response.people if p in filters_available['people']]
        response.entities = [e for e in response.entities if e in filters_available['entities']]
        return response.dict()
    except ValidationError:
        return {}


# **************************************************
# ************* REALTIME V2 LANGGRAPH **************
# **************************************************

def extract_question_from_transcript(uid: str, segments: List[TranscriptSegment]) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    prompt = f'''
{user_name} is having a conversation.

This is what you know about {user_name}: {facts_str}

You will be the transcript of a recent conversation between {user_name} and a few people, \
your task is to understand the last few exchanges, and identify in order to provide advice to {user_name}, what other things about {user_name} \
you should know.

For example, if the conversation is about a new job, you should output a question like "What discussions have I had about job search?".
For example, if the conversation is about a new programming languages, you should output a question like "What have I chatted about programming?".

Make sure as a first step, you infer and fix the raw transcript errors and then proceed to figure out the most meaningful question to ask.

You must output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

Conversation:
{TranscriptSegment.segments_as_string(segments)}

text

Collapse

Wrap

Copy
'''.replace('    ', '').strip()
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question


class OutputMessage(BaseModel):
    message: str = Field(description='The message to be sent to the user.', max_length=200)


def provide_advice_message(uid: str, segments: List[TranscriptSegment], context: str) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    transcript = TranscriptSegment.segments_as_string(segments)
    prompt = f"""
You are a brutally honest, very creative, sometimes funny, indefatigable personal life coach who helps people improve their own agency in life, \
pulling in pop culture references and inspirational business and life figures from recent history, mixed in with references to recent personal memories,
to help drive the point across.

{facts_str}

{user_name} just had a conversation and is asking for advice on what to do next.

In order to answer you must analyze:
- The conversation transcript.
- The related conversations from previous days.
- The facts you know about {user_name}.

You start all your sentences with:
- "If I were you, I would do this..."
- "I think you should do x..."
- "I believe you need to do y..."

Your sentences are short, to the point, and very direct, at most 20 words.
MUST OUTPUT 20 words or less.

Conversation Transcript:
{transcript}

Context:
{context}

text

Collapse

Wrap

Copy
""".replace('    ', '').strip()
    return llm_mini.with_structured_output(OutputMessage).invoke(prompt).message


# **************************************************
# ************* PROACTIVE NOTIFICATION PLUGIN **************
# **************************************************

def get_proactive_message(uid: str, plugin_prompt: str, params: [str], context: str,
                          chat_messages: List[Message]) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    prompt = plugin_prompt
    for param in params:
        if param == "user_name":
            prompt = prompt.replace("{{user_name}}", user_name)
            continue
        if param == "user_facts":
            prompt = prompt.replace("{{user_facts}}", facts_str)
            continue
        if param == "user_context":
            prompt = prompt.replace("{{user_context}}", context if context else "")
            continue
        if param == "user_chat":
            prompt = prompt.replace("{{user_chat}}",
                                    Message.get_messages_as_string(chat_messages) if chat_messages else "")
            continue
    prompt = prompt.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


# **************************************************
# *************** APPS AI GENERATE *****************
# **************************************************

def generate_description(app_name: str, description: str) -> str:
    prompt = f"""
You are an AI assistant specializing in crafting detailed and engaging descriptions for apps.
You will be provided with the app's name and a brief description which might not be that good. Your task is to expand on the given information, creating a captivating and detailed app description that highlights the app's features, functionality, and benefits.
The description should be concise, professional, and not more than 40 words, ensuring clarity and appeal. Respond with only the description, tailored to the app's concept and purpose.
App Name: {app_name}
Description: {description}
"""
    prompt = prompt.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content


# **********************************
# ******** PROMPT OPTIMIZER ********
# **********************************

# Expanded candidate prompt templates for QA tasks
CANDIDATE_PROMPTS = {
    "markdown_prioritized": (
        "You are an assistant that uses markdown formatting effectively. "
        "Answer the question with clarity and include markdown where it improves readability.\n\n"
        "Question: {question}\n"
        "Context: {context}\n\n"
        "Answer:"
    ),
    "plain_text": (
        "You are an assistant that answers clearly without markdown formatting. "
        "Answer the question concisely in plain text.\n\n"
        "Question: {question}\n"
        "Context: {context}\n\n"
        "Answer:"
    ),
    "data_driven": (
        "You are an assistant that leverages user data for personalized answers. "
        "Use the context and facts to tailor your response to the user.\n\n"
        "Question: {question}\n"
        "Context: {context}\n"
        "User Facts: {user_facts}\n\n"
        "Answer:"
    ),
}


class PromptOptimizer:
    def __init__(self, candidate_prompts: Dict[str, str], redis_client: redis.Redis):
        self.candidate_prompts = candidate_prompts
        self.redis_client = redis_client
        self.prompt_total_scores = self._load_from_redis("prompt_total_scores", {name: 0.0 for name in candidate_prompts})
        self.prompt_counts = self._load_from_redis("prompt_counts", {name: 0 for name in candidate_prompts})
        self.best_prompt_name = self._get_best_prompt_name()

    def _load_from_redis(self, key: str, default: Dict) -> Dict:
        """Load data from Redis or return default if not present."""
        try:
            data = self.redis_client.get(key)
            return json.loads(data) if data else default
        except Exception as e:
            print(f"Error loading {key} from Redis: {e}")
            return default

    def _save_to_redis(self, key: str, data: Dict):
        """Save data to Redis."""
        try:
            self.redis_client.set(key, json.dumps(data))
        except Exception as e:
            print(f"Error saving {key} to Redis: {e}")

    def update_feedback(self, candidate_name: str, user_rating: float, response_text: str):
        """Update feedback for a candidate prompt with validation."""
        if not isinstance(user_rating, (int, float)) or not 1 <= user_rating <= 5:
            raise ValueError("User rating must be a number between 1 and 5")
        if candidate_name not in self.candidate_prompts:
            raise ValueError(f"Unknown candidate prompt: {candidate_name}")

        auto_md_score = self.evaluate_markdown_usage(response_text)
        combined_score = (user_rating + (auto_md_score * 5)) / 2  # Scale auto score to 1-5
        self.prompt_total_scores[candidate_name] += combined_score
        self.prompt_counts[candidate_name] += 1

        self._save_to_redis("prompt_total_scores", self.prompt_total_scores)
        self._save_to_redis("prompt_counts", self.prompt_counts)
        self.best_prompt_name = self._get_best_prompt_name()

    def _get_best_prompt_name(self) -> str:
        """Determine the best prompt based on average score."""
        return max(
            self.candidate_prompts.keys(),
            key=lambda name: self.prompt_total_scores[name] / (self.prompt_counts[name] or 1),
            default=list(self.candidate_prompts.keys())[0]
        )

    def get_best_prompt(self) -> str:
        """Return the best prompt template string."""
        if self.best_prompt_name is None:
            self.best_prompt_name = list(self.candidate_prompts.keys())[0]
        return self.candidate_prompts[self.best_prompt_name]

    @staticmethod
    def evaluate_markdown_usage(response_text: str) -> float:
        """Evaluate markdown usage based on meaningful structures."""
        if not response_text:
            return 0.0
        score = 0.0
        # Check for headers (e.g., #, ##)
        if re.search(r'^#{1,3}\s', response_text, re.MULTILINE):
            score += 0.3
        # Check for lists (e.g., - or *)
        if re.search(r'^[-*]\s', response_text, re.MULTILINE):
            score += 0.3
        # Check for code blocks (```)
        if '```' in response_text:
            score += 0.4
        return min(score, 1.0)


# Instantiate optimizer with Redis persistence
prompt_optimizer = PromptOptimizer(CANDIDATE_PROMPTS, redis_client)


def qa_with_optimized_prompt(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, 
                             messages: List[Message] = [], tz: Optional[str] = "UTC", user_rating: Optional[float] = None) -> str:
    """Use optimized prompt for QA, update feedback, and log metrics."""
    try:
        user_name, facts_str = get_prompt_facts(uid)
        prompt_template = prompt_optimizer.get_best_prompt()

        # Fill prompt with available data
        prompt = prompt_template.format(
            question=question,
            context=context,
            user_facts=facts_str if "user_facts" in prompt_template else ""
        )

        response = llm_medium.invoke(prompt).content

        if user_rating is not None:
            prompt_optimizer.update_feedback(prompt_optimizer.best_prompt_name, user_rating, response)

        log_evaluation_metrics(prompt, response, question, context, uid, tz)
        return response
    except Exception as e:
        print(f"Error in qa_with_optimized_prompt: {e}")
        return "Sorry, something went wrong while processing your request."


def log_evaluation_metrics(prompt: str, response: str, question: str, context: str, uid: str, tz: str):
    """Log metrics to a simulated LangSmith-like dashboard."""
    metrics = {
        "uid": uid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "response": response,
        "question": question,
        "context": context,
        "tz": tz,
        "markdown_score": PromptOptimizer.evaluate_markdown_usage(response),
        "response_time": 0.5,  # Placeholder; measure actual time in production
        "chatgpt_comparison": "Pending"  # Placeholder for actual comparison
    }
    # Simulate LangSmith integration (replace with actual API call)
    try:
        # In production: langsmith_client.log(metrics)
        print("Evaluation Metrics:", json.dumps(metrics, indent=2))
    except Exception as e:
        print(f"Error logging metrics: {e}")


# Example usage
if __name__ == "__main__":
    uid = "user123"
    question = "What is the best way to integrate markdown in responses?"
    context = "Previous conversation context goes here..."
    simulated_user_rating = 4.0
    answer = qa_with_optimized_prompt(uid, question, context, user_rating=simulated_user_rating)
    print("Final Answer:", answer)
