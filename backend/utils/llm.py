import json
import re
from datetime import datetime, timezone
from typing import List, Optional

import tiktoken
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
from models.trend import TrendEnum, ceo_options, company_options, software_product_options, hardware_product_options, \
    ai_product_options, TrendType
from utils.memories.facts import get_prompt_facts
from utils.prompts import extract_facts_prompt, extract_learnings_prompt

llm_mini = ChatOpenAI(model='gpt-4o-mini')
llm_large = ChatOpenAI(model='o1-preview')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
parser = PydanticOutputParser(pydantic_object=Structured)

encoding = tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


# TODO: include caching layer, redis


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

    parser = PydanticOutputParser(pydantic_object=DiscardMemory)
    prompt = ChatPromptTemplate.from_messages([
        '''
    You will be given a conversation transcript, and your task is to determine if the conversation is worth storing as a memory or not.
    It is not worth storing if there are no interesting topics, facts, or information, in that case, output discard = True.
    
    Transcript: ```{transcript}```
    
    {format_instructions}'''.replace('    ', '').strip()
    ])
    chain = prompt | llm_mini | parser
    try:
        response: DiscardMemory = chain.invoke({
            'transcript': transcript.strip(),
            'format_instructions': parser.get_format_instructions(),
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
    ```
    ${conversation_history}
    ```
    """.replace('    ', '').strip()
    # print(prompt)
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


# *********************************************
# ************* RETRIEVAL + CHAT **************
# *********************************************


class RequiresContext(BaseModel):
    value: bool = Field(description="Based on the conversation, this tells if context is needed to respond")


class TopicsContext(BaseModel):
    topics: List[CategoryEnum] = Field(default=[], description="List of topics.")


class DatesContext(BaseModel):
    dates_range: List[datetime] = Field(default=[],
                                        examples=[['2024-12-23T00:00:00+07:00', '2024-12-23T23:59:00+07:00']],
                                        description="Dates range. (Optional)",)


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

    Your task is to to find the dates range in which the current conversation needs context about, in order to answer the most recent user request.

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
    You MUST determine the appropriate date range in {tz} that provides context for answering the question provided.

    Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

    Question:
    ```
    {question}
    ```

    '''.replace('    ', '').strip()

    # print(prompt)
    # print(llm_mini.invoke(prompt).content)
    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range

def retrieve_context_dates_by_question_v2(question: str, tz: str) -> List[datetime]:
    prompt = f'''
    **Task:** Determine the appropriate date range in UTC that provides context for answering the question.

    **Instructions:**

     1. Current Date Reference: Utilize today's date, {datetime.now(timezone.utc).strftime('%Y-%m-%d')} in UTC. Note that the question is posed in the question timezone: {tz}.
     2. Scope of Inquiry: Disregard any queries concerning historical events or future projections. For such inquiries, return an empty list.
     3. Date Range Specification: Present the date range in UTC format.
     4. Response Format: Use the format [YYYY-MM-DDTHH:MM:SSZ, YYYY-MM-DDTHH:MM:SSZ].

    **Clarifications:**

    - "Today" refers to the current date.
    - "Tomorrow" indicates the day following today.
    - "Yesterday" signifies the day preceding today.
    - "Next week" starts on the upcoming Monday.

    **Examples:**

    - Example 1:

      - Today: 2024-12-20 in UTC
      - Question's timezone: America/Los_Angeles
      - Question: What memories were captured on December 18, 2024, that you would like recapped?
      - Answer: [2024-12-18T08:00:00Z, 2024-12-19T08:00:00Z]

    - Example 2:

      -Today: 2024-12-20 in UTC
      -Question's timezone: America/Los_Angeles
      -Question: What memories were captured on yesterday, that you would like recapped?
      -Answer: [2024-12-19T08:00:00Z, 2024-12-20T08:00:00Z]

    **Question's timezone:**
    ```
    {tz}
    ```

    **Question:**
    ```
    {question}
    ```
    '''.replace('    ', '').strip()

    # print(prompt)
    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range

def retrieve_context_dates_by_question_v1(question: str, tz: str) -> List[datetime]:
    prompt = f'''
    Task: Identify the relevant date range needed to provide context for answering the user's recent question.

    Instructions:

    1. Use the current date for reference, which is {datetime.now(timezone.utc).strftime('%Y-%m-%d')} in UTC. Convert the user's timezone, {tz}, to UTC and respond accordingly.

    2. Ignore requests related to historical or future events. For these, return an empty list.

    3. Provide the date range in UTC

    User's Question:
    {question}
    '''.replace('    ', '').strip()

    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range


class SummaryOutput(BaseModel):
    summary: str = Field(description="The extracted content, maximum 500 words.")


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
    with_parser = llm_mini.with_structured_output(SummaryOutput)
    response: SummaryOutput = with_parser.invoke(prompt)
    return response.summary


def answer_simple_message(uid: str, messages: List[Message], plugin: Optional[Plugin] = None) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )
    user_name, facts_str = get_prompt_facts(uid)

    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    prompt = f"""
    You are an assistant for engaging personal conversations. 
    You are made for {user_name}, {facts_str}

    Use what you know about {user_name}, to continue the conversation, feel free to ask questions, share stories, or just say hi.
    {plugin_info}

    Conversation History:
    {conversation_history}

    Answer:
    """.replace('    ', '').strip()
    # print(prompt)
    return llm_mini.invoke(prompt).content


def answer_omi_question(messages: List[Message], context: str) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )

    prompt = f"""
    You are an assistant for answering questions about the app Omi, also known as Friend.
    Continue the conversation, answering the question based on the context provided.

    Context:
    ```
    {context}
    ```

    Conversation History:
    {conversation_history}

    Answer:
    """.replace('    ', '').strip()
    return llm_mini.invoke(prompt).content

def qa_rag(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False, messages: List[Message] = [], tz: Optional[str] = "UTC") -> str:
    user_name, facts_str = get_prompt_facts(uid)
    facts_str = '\n'.join(facts_str.split('\n')[1:]).strip()

    # Use as template (make sure it varies every time): "If I were you $user_name I would do x, y, z."
    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    # Ref: https://www.reddit.com/r/perplexity_ai/comments/1hi981d
    cited_prompt = """
    Cite in memories using [index] at the end of sentences when needed, for example "You discussed optimizing firmware with your teammate yesterday[1][2]". NO SPACE between the last word and the citation. Cite the most relevant memories that answer the Question. Avoid citing irrelevant memories.
    """ if cited else ""

    prompt = f"""
    You are an assistant for question-answering tasks.
    You answer Question in the most personalized way possible, using the conversations(memory) provided.

    You will be provided previous messages between you and user to help you answer the Question. \
    It's IMPORTANT to refine the Question base on the last messages only before anwser it.

    {cited_prompt}

    Keep the answer concise.

    Use markdown to bold text sparingly, primarily for emphasis within sentences.

    {plugin_info}

    **Question:**
    ```
    {question}
    ```

    **Conversations(Memories):**
    ---
    {context}
    ---

    **Previous messages:**
    ---
     {Message.get_messages_as_string(messages)}
    ---

    Use the following User Facts if relevant to the Question.

    **User Facts:**
    ---
    {facts_str.strip()}
    ---

    Question's timezone: {tz}

    Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

    Anwser:
    """.replace('    ', '').replace('\n\n\n', '\n\n').strip()
    # print('qa_rag prompt', prompt)
    return llm_large.invoke(prompt).content


def qa_rag_v3(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False, messages: List[Message] = [], tz: Optional[str] = "UTC") -> str:
    user_name, facts_str = get_prompt_facts(uid)
    facts_str = '\n'.join(facts_str.split('\n')[1:]).strip()

    # Use as template (make sure it varies every time): "If I were you $user_name I would do x, y, z."
    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    # Ref: https://www.reddit.com/r/perplexity_ai/comments/1hi981d
    cited_prompt = """
    Cite in memories using [index] at the end of sentences when needed, for example "You discussed optimizing firmware with your teammate yesterday[1][2]". NO SPACE between the last word and the citation. Cite the most relevant memories that answer the Question. Avoid citing irrelevant memories.
    """ if cited else ""

    prompt = f"""
    You are an assistant for question-answering tasks.
    You answer Question in the most personalized way possible, using the conversations(memory) provided.

    You will be provided previous messages between you and user to help you answer the Question. \
    It's IMPORTANT to refine the Question base on the last messages only before anwser it.

    {cited_prompt}

    Use three sentences maximum and keep the answer concise.

    Use markdown to bold text sparingly, primarily for emphasis within sentences.

    {plugin_info}

    **Question:**
    ```
    {question}
    ```

    **Conversations(Memories):**
    ---
    {context}
    ---

    **Previous messages:**
    ---
     {Message.get_messages_as_string(messages)}
    ---

    Use the following User Facts if relevant to the Question.

    **User Facts:**
    ---
    {facts_str.strip()}
    ---

    Question's timezone: {tz}

    Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

    Anwser:
    """.replace('    ', '').replace('\n\n\n', '\n\n').strip()
    # print('qa_rag prompt', prompt)
    return ChatOpenAI(model='gpt-4o').invoke(prompt).content

def qa_rag_v2(uid: str, question: str, context: str, plugin: Optional[Plugin] = None, cited: Optional[bool] = False) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    facts_str = '\n'.join(facts_str.split('\n')[1:]).strip()

    # Use as template (make sure it varies every time): "If I were you $user_name I would do x, y, z."
    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    # Ref: https://www.reddit.com/r/perplexity_ai/comments/1hi981d
    cited_prompt = """
    Cite conversations(memories) using [index] at the end of sentences when needed, for example "You discussed optimizing firmware with your teammate yesterday[1][2]". NO SPACE between the last word and the citation.
    Cite the most relevant conversations(memories) that answer the Question. Avoid citing irrelevant conversations(memories).
    Cite only in the conversations (memories), not in the User Fact.
    """ if cited else ""

    prompt = f"""
    You are an assistant for question-answering tasks.
    You answer Question in the most personalized way possible, using the conversations(memory) provided.

    {cited_prompt}

    Use three sentences maximum and keep the answer concise.

    {plugin_info}

    **Question:**
    ```
    {question}
    ```

    Use the following User Facts if relevant to the Question:

    **User Facts:**
    ```
    {facts_str.strip()}
    ```

    **Conversations:**
    ```
    {context}
    ```

    Answer:
    """.replace('    ', '').replace('\n\n\n', '\n\n').strip()
    # print('qa_rag prompt', prompt)
    return ChatOpenAI(model='gpt-4o').invoke(prompt).content

def qa_rag_v1(uid: str, question: str, context: str, plugin: Optional[Plugin] = None) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    facts_str = '\n'.join(facts_str.split('\n')[1:]).strip()

    # Use as template (make sure it varies every time): "If I were you $user_name I would do x, y, z."
    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    prompt = f"""
    You are an assistant for question-answering tasks. 
    You answer question in the most personalized way possible, using the context provided.

    If the user is asking for advice/recommendations, you must always answer, even if there's no context at all.
    Never say that you don't have enough information, unless the user is referring or specifically asking about stuff in the past, and nothing related was provided.

    Use three sentences maximum and keep the answer concise.

    {plugin_info}

    Question:
    {question}

    Context:
    ```
    **User Facts:**
    {facts_str.strip()}

    **Related Conversations:**
    {context}
    ```
    Answer:
    """.replace('    ', '').replace('\n\n\n', '\n\n').strip()
    # print('qa_rag prompt', prompt)
    return ChatOpenAI(model='gpt-4o').invoke(prompt).content


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
    ```
    {context}
    ```
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
    # print('new_facts_extractor', uid, 'segments', len(segments), user_name, 'len(facts_str)', len(facts_str))
    if user_name is None or facts_str is None:
        user_name, facts_str = get_prompt_facts(uid)

    content = TranscriptSegment.segments_as_string(segments, user_name=user_name)
    if not content or len(content) < 25:  # less than 5 words, probably nothing
        return []
    # TODO: later, focus a lot on user said things, rn is hard because of speech profile accuracy
    # TODO: include negative facts too? Things the user doesn't like?
    # TODO: make it more strict?

    try:
        parser = PydanticOutputParser(pydantic_object=Facts)
        chain = extract_facts_prompt | llm_mini | parser
        # with_parser = llm_mini.with_structured_output(Facts)
        response: Facts = chain.invoke({
            'user_name': user_name,
            'conversation': content,
            'facts_str': facts_str,
            'format_instructions': parser.get_format_instructions(),
        })
        # for fact in response:
        #     fact.content = fact.content.replace(user_name, '').replace('The User', '').replace('User', '').strip()
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
        parser = PydanticOutputParser(pydantic_object=Learnings)
        chain = extract_learnings_prompt | llm_mini | parser
        response: Learnings = chain.invoke({
            'user_name': user_name,
            'conversation': content,
            'learnings_str': learnings_str,
            'format_instructions': parser.get_format_instructions(),
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
            if item.topic not in [e for e in (
                    ceo_options + company_options + software_product_options + hardware_product_options + ai_product_options)]:
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
        # trim to last 500 words
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
    # user last messages
    user_message_idx = len(messages)
    for i in range(len(messages)-1, -1,-1):
        if messages[i].sender == MessageSender.ai:
            break
        if messages[i].sender == MessageSender.human:
            user_message_idx = i
    user_last_messages = messages[user_message_idx:]
    if len(user_last_messages) == 0:
        return ""

    prompt = f'''
    You will be given a recent conversation within a user and an AI, \
    there could be a few messages exchanged, and partly built up the proper question, \
    your task is to understand the user last messages, and identify the question or follow-up question the user is asking. \

    You MUST keep the original `date time term`.

    If the user's last message is a complete question, maintain the original version as accurately as possible. Avoid adding unnecessary words.

    You will be provided previous messages between you and user to help you answer the Question. \
    It's super IMPORTANT to refine the Question to be full context with the last messages only.

    If the user is not asking a question or does not want to follow up, respond with an empty message.

    Output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

    Example 1:
    User last messages:
    ```According to WHOOP, my HRV this Sunday was the highest it's been in a month. Here's what I did:

    Attended an outdoor party (cold weather, talked a lot more than usual).
    Smoked weed (unusual for me).
    Drank lots of relaxing tea.

    Can you prioritize each activity on a 0-10 scale for how much it might have influenced my HRV?
    ```
    Expected output: "How should each activity (going to a party and talking a lot, smoking weed, and drinking lots of relaxing tea) be prioritized on a scale of 0-10 in terms of their impact on my HRV, considering the recent activities that led to the highest HRV this month?"

    **The user last messages:**
    ```
    {Message.get_messages_as_string(user_last_messages)}
    ```

    **Previous messages:**
    ```
    {Message.get_messages_as_string(messages)}
    ```

    **Date time term:** today, my day, my week, this week, this day, etc.

    '''.replace('    ', '').strip()
    # print(prompt)
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question

def extract_question_from_conversation_v3(messages: List[Message]) -> str:
    # user last messages
    user_message_idx = len(messages)
    for i in range(len(messages)-1, -1,-1):
        if messages[i].sender == MessageSender.ai:
            break
        if messages[i].sender == MessageSender.human:
            user_message_idx = i
    user_last_messages = messages[user_message_idx:]
    if len(user_last_messages) == 0:
        return ""

    prompt = f'''
    You will be given a recent conversation within a user and an AI, \
    there could be a few messages exchanged, and partly built up the proper question, \
    your task is to understand the user last messages, and identify the question or follow-up question the user is asking. \

    If the user's last message is a complete question, maintain the original version as accurately as possible. Avoid adding unnecessary words.

    It is super important that THE QUESTION MUST BE FULL CONTEXT base on the user last messages.

    If the user is not asking a question or does not want to follow up, respond with an empty message.

    Output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

    Example 1:
    User last messages:
    ```According to WHOOP, my HRV this Sunday was the highest it's been in a month. Here's what I did:

    Attended an outdoor party (cold weather, talked a lot more than usual).
    Smoked weed (unusual for me).
    Drank lots of relaxing tea.

    Can you prioritize each activity on a 0-10 scale for how much it might have influenced my HRV?
    ```
    Expected output: "How should each activity (going to a party and talking a lot, smoking weed, and drinking relaxing tea) be prioritized on a scale of 0-10 in terms of their impact on my HRV?"

    The user last messages:
    ```
    {Message.get_messages_as_string(user_last_messages)}
    ```

    Conversation:
    ```
    {Message.get_messages_as_string(messages)}
    ```

    '''.replace('    ', '').strip()
    # print(prompt)
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question


def extract_question_from_conversation_v2(messages: List[Message]) -> str:
    # user last messages
    user_message_idx = len(messages)
    for i in range(len(messages)-1, -1,-1):
        if messages[i].sender == MessageSender.ai:
            break
        if messages[i].sender == MessageSender.human:
            user_message_idx = i
    user_last_messages = messages[user_message_idx:]
    if len(user_last_messages) == 0:
        return ""

    prompt = f'''
    You will be given a recent conversation within a user and an AI, \
    there could be a few messages exchanged, and partly built up the proper question, \
    your task is to understand the user last messages, and identify the single question or follow-up question the user is asking. \

    If the user is not asking a question or does not want to follow up, respond with an empty message.

    Output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

    The user last messages:
    ```
    {Message.get_messages_as_string(user_last_messages)}
    ```

    Conversation:
    ```
    {Message.get_messages_as_string(messages)}
    ```

    '''.replace('    ', '').strip()
    # print(prompt)
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question


def extract_question_from_conversation_v1(messages: List[Message]) -> str:
    prompt = f'''
    You will be given a recent conversation within a user and an AI, \
    there could be a few messages exchanged, and partly built up the proper question, \
    your task is to understand THE LAST FEW MESSAGES, and identify the single question or follow-up question the user is asking. \

    If the user is not asking a question or does not want to follow up, respond with an empty message.

    Output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

    Conversation:
    ```
    {Message.get_messages_as_string(messages)}
    ```
    '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question

def retrieve_metadata_fields_from_transcript(
    uid: str, created_at: datetime, transcript_segment: List[dict], tz: str
) -> ExtractedInformation:
    transcript = ''
    for segment in transcript_segment:
        transcript += f'{segment["text"].strip()}\n\n'

    # TODO: ask it to use max 2 words? to have more standardization possibilities
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
    ```
    {transcript}
    ```
    '''.replace('    ', '')
    try:
        result: ExtractedInformation = llm_mini.with_structured_output(ExtractedInformation).invoke(prompt)
    except Exception as e:
        print('e', e)
        return {'people': [], 'topics': [], 'entities': [], 'dates': []}

    def normalize_filter(value: str) -> str:
        # Convert to lowercase and strip whitespace
        value = value.lower().strip()

        # Remove special characters and extra spaces
        value = re.sub(r'[^\w\s-]', '', value)
        value = re.sub(r'\s+', ' ', value)

        # Remove common filler words
        filler_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to'}
        value = ' '.join(word for word in value.split() if word not in filler_words)

        # Standardize common variations
        value = value.replace('artificial intelligence', 'ai')
        value = value.replace('machine learning', 'ml')
        value = value.replace('natural language processing', 'nlp')

        return value.strip()

    metadata = {
        'people': [normalize_filter(p) for p in result.people],
        'topics': [normalize_filter(t) for t in result.topics],
        'entities': [normalize_filter(e) for e in result.topics],
        'dates': []
    }
    # 'dates': [date.strftime('%Y-%m-%d') for date in result.dates],
    for date in result.dates:
        try:
            date = datetime.strptime(date, '%Y-%m-%d')
            if date.year > 2025:
                continue
            metadata['dates'].append(date.strftime('%Y-%m-%d'))
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

    return metadata


def select_structured_filters(question: str, filters_available: dict) -> dict:
    prompt = f'''
    Based on a question asked by the user to an AI, the AI needs to search for the user information related to topics, entities, people, and dates that will help it answering.
    Your task is to identify the correct fields that can be related to the question and can help answering.
    
    You must choose for each field, only the ones available in the JSON below.
    Find as many as possible that can relate to the question asked.
    ```
    {json.dumps(filters_available, indent=2)}
    ```

    Question: {question}
    '''.replace('    ', '').strip()
    # print(prompt)
    with_parser = llm_mini.with_structured_output(FiltersToUse)
    try:
        response: FiltersToUse = with_parser.invoke(prompt)
        # print('select_structured_filters:', response.dict())
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
    ```
    {TranscriptSegment.segments_as_string(segments)}
    ```
    '''.replace('    ', '').strip()
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question


class OutputMessage(BaseModel):
    message: str = Field(description='The message to be sent to the user.', max_length=200)


def provide_advice_message(uid: str, segments: List[TranscriptSegment], context: str) -> str:
    user_name, facts_str = get_prompt_facts(uid)
    transcript = TranscriptSegment.segments_as_string(segments)
    # TODO: tweak with different type of requests, like this, or roast, or praise or emotional, etc.

    prompt = f"""
    You are a brutally honest, very creative, sometimes funny, indefatigable personal life coach who helps people improve their own agency in life, \
    pulling in pop culture references and inspirational business and life figures from recent history, mixed in with references to recent personal memories, 
    to help drive the point across. 
    
    {facts_str}
    
    {user_name} just had a conversation and is asking for advice on what to do next.
    
    In order to answer you must analyize:
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
    ```
    {context}
    ```
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
    # print(prompt)

    return llm_mini.invoke(prompt).content
