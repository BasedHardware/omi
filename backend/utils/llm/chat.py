from .clients import llm_mini, llm_mini_stream, llm_medium_stream, llm_medium
import json
import re
import os
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError

import database.users as users_db
import database.notifications as notification_db
import database.goals as goals_db
from database.redis_db import add_filter_category_item
from database.auth import get_user_name
from models.app import App
from models.chat import Message, MessageSender, PageContext
from models.conversation import CategoryEnum, Conversation, ActionItem, Event, ConversationPhoto
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.llms.memory import get_prompt_memories


# ****************************************
# ************* CHAT BASICS **************
# ****************************************


def initial_chat_message(uid: str, plugin: Optional[App] = None, prev_messages_str: str = '') -> str:
    user_name, memories_str = get_prompt_memories(uid)
    if plugin is None:
        prompt = f"""
You are 'Omi', a friendly and helpful assistant who aims to make {user_name}'s life better 10x.
You know the following about {user_name}: {memories_str}.

{prev_messages_str}

Compose {"an initial" if not prev_messages_str else "a follow-up"} message to {user_name} that fully embodies your friendly and helpful personality. Use warm and cheerful language, and include light humor if appropriate. The message should be short, engaging, and make {user_name} feel welcome. Do not mention that you are an assistant or that this is an initial message; just {"start" if not prev_messages_str else "continue"} the conversation naturally, showcasing your personality.
"""
    else:
        prompt = f"""
You are '{plugin.name}', {plugin.chat_prompt}.
You know the following about {user_name}: {memories_str}.

{prev_messages_str}

As {plugin.name}, fully embrace your personality and characteristics in your {"initial" if not prev_messages_str else "follow-up"} message to {user_name}. Use language, tone, and style that reflect your unique personality traits. {"Start" if not prev_messages_str else "Continue"} the conversation naturally with a short, engaging message that showcases your personality and humor, and connects with {user_name}. Do not mention that you are an AI or that this is an initial message.
"""
    prompt = prompt.strip()
    return llm_medium.invoke(prompt).content


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


def retrieve_is_an_omi_question(question: str) -> bool:
    prompt = f'''
    Task: Determine if the user is asking about the Omi/Friend app itself (product features, functionality, purchasing) 
    OR if they are asking about their personal data/memories stored in the app OR requesting an action/task.

    CRITICAL DISTINCTION:
    - Questions ABOUT THE APP PRODUCT = True (e.g., "How does Omi work?", "What features does Omi have?")
    - Questions ABOUT USER'S PERSONAL DATA = False (e.g., "What did I say?", "How many conversations do I have?")
    - ACTION/TASK REQUESTS = False (e.g., "Remind me to...", "Create a task...", "Set an alarm...")

    **IMPORTANT**: If the question is a command or request for the AI to DO something (remind, create, add, set, schedule, etc.), 
    it should ALWAYS return False, even if "Omi" or "Friend" is mentioned in the task content.

    Examples of Omi/Friend App Questions (return True):
    - "How does Omi work?"
    - "What can Omi do?"
    - "How can I buy the device?"
    - "Where do I get Friend?"
    - "What features does the app have?"
    - "How do I set up Omi?"
    - "Does Omi support multiple languages?"
    - "What is the battery life?"
    - "How do I connect my device?"

    Examples of Personal Data Questions (return False):
    - "How many conversations did I have last month?"
    - "What did I talk about yesterday?"
    - "Show me my memories from last week"
    - "Who did I meet with today?"
    - "What topics have I discussed?"
    - "Summarize my conversations"
    - "What did I say about work?"
    - "When did I last talk to John?"

    Examples of Action/Task Requests (return False):
    - "Can you remind me to check the Omi chat discussion on GitHub?"
    - "Remind me to update the Omi firmware"
    - "Create a task to review Friend documentation"
    - "Set an alarm for my Omi meeting"
    - "Add to my list: check Omi updates"
    - "Schedule a reminder about the Friend app launch"

    KEY RULES: 
    1. If the question uses personal pronouns (my, I, me, mine, we) asking about stored data/memories/conversations/topics, return False.
    2. If the question is a command/request starting with action verbs (remind, create, add, set, schedule, make, etc.), return False.
    3. Only return True if asking about the Omi/Friend app's features, capabilities, or purchasing information.

    User's Question:
    {question}
    
    Is this asking about the Omi/Friend app product itself?
    '''.replace(
        '    ', ''
    ).strip()
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


def retrieve_context_dates_by_question(question: str, tz: str) -> List[datetime]:
    prompt = f'''
    You MUST determine the appropriate date range in {tz} that provides context for answering the <question> provided.

    If the <question> does not reference a date or a date range, respond with an empty list: []

    Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}

    <question>
    {question}
    </question>

    '''.replace(
        '    ', ''
    ).strip()

    # print(prompt)
    # print(llm_mini.invoke(prompt).content)
    with_parser = llm_mini.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range


class SummaryOutput(BaseModel):
    summary: str = Field(description="The extracted content, maximum 500 words.")


def chunk_extraction(segments: List[TranscriptSegment], topics: List[str], people: List[Person] = None) -> str:
    content = TranscriptSegment.segments_as_string(segments, people=people)
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


def _get_answer_simple_message_prompt(uid: str, messages: List[Message], app: Optional[App] = None) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )
    user_name, memories_str = get_prompt_memories(uid)

    plugin_info = ""
    if app:
        plugin_info = f"Your name is: {app.name}, and your personality/description is '{app.description}'.\nMake sure to reflect your personality in your response.\n"

    return f"""
    You are an assistant for engaging personal conversations.
    You are made for {user_name}, {memories_str}

    Use what you know about {user_name}, to continue the conversation, feel free to ask questions, share stories, or just say hi.
    {plugin_info}

    Conversation History:
    {conversation_history}

    Answer:
    """.replace(
        '    ', ''
    ).strip()


def answer_simple_message(uid: str, messages: List[Message], plugin: Optional[App] = None) -> str:
    prompt = _get_answer_simple_message_prompt(uid, messages, plugin)
    return llm_mini.invoke(prompt).content


def answer_simple_message_stream(uid: str, messages: List[Message], plugin: Optional[App] = None, callbacks=[]) -> str:
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
    ```
    {context}
    ```

    Conversation History:
    {conversation_history}

    Answer:
    """.replace(
        '    ', ''
    ).strip()


def answer_omi_question(messages: List[Message], context: str) -> str:
    prompt = _get_answer_omi_question_prompt(messages, context)
    return llm_mini.invoke(prompt).content


def answer_omi_question_stream(messages: List[Message], context: str, callbacks: []) -> str:
    prompt = _get_answer_omi_question_prompt(messages, context)
    return llm_mini_stream.invoke(prompt, {'callbacks': callbacks}).content


def _get_qa_rag_prompt(
    uid: str,
    question: str,
    context: str,
    plugin: Optional[App] = None,
    cited: Optional[bool] = False,
    messages: List[Message] = [],
    tz: Optional[str] = "UTC",
) -> str:
    user_name, memories_str = get_prompt_memories(uid)
    memories_str = '\n'.join(memories_str.split('\n')[1:]).strip()

    # Use as template (make sure it varies every time): "If I were you $user_name I would do x, y, z."
    context = context.replace('\n\n', '\n').strip()
    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    # Ref: https://www.reddit.com/r/perplexity_ai/comments/1hi981d
    cited_instruction = """
    - You MUST cite the most relevant <memories> that answer the question. \
      - Only cite in <memories> not <user_facts>, not <previous_messages>.
      - Cite in memories using [index] at the end of sentences when needed, for example "You discussed optimizing firmware with your teammate yesterday[1][2]".
      - NO SPACE between the last word and the citation.
      - Avoid citing irrelevant memories.
    """

    return (
        f"""
    <assistant_role>
        You are an assistant for question-answering tasks.
    </assistant_role>

    <task>
        Write an accurate, detailed, and comprehensive response to the <question> in the most personalized way possible, using the <memories>, <user_facts> provided.
    </task>

    <instructions>
    - Refine the <question> based on the last <previous_messages> before answering it.
    - DO NOT use the AI's message from <previous_messages> as references to answer the <question>
    - Use <question_timezone> and <current_datetime_utc> to refer to the time context of the <question>
    - It is EXTREMELY IMPORTANT to directly answer the question, keep the answer concise and high-quality.
    - NEVER say "based on the available memories". Get straight to the point.
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
     - Goals and Achievements
     - Mood Tracker
     - Gratitude Log
     - Lessons Learned
    </reports_instructions>

    <question>
    {question}
    <question>

    <memories>
    {context}
    </memories>

    <previous_messages>
    {Message.get_messages_as_xml(messages)}
    </previous_messages>

    <user_facts>
    [Use the following User Facts if relevant to the <question>]
        {memories_str.strip()}
    </user_facts>

    <current_datetime_utc>
        Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
    </current_datetime_utc>

    <question_timezone>
        Question's timezone: {tz}
    </question_timezone>

    <answer>
    """.replace(
            '    ', ''
        )
        .replace('\n\n\n', '\n\n')
        .strip()
    )


def _get_agentic_qa_prompt(
    uid: str,
    app: Optional[App] = None,
    messages: List[Message] = None,
    context: Optional[PageContext] = None
) -> str:
    """
    Build the system prompt for the agentic agent.

    Args:
        uid: User ID
        app: Optional app/plugin for personalized behavior
        messages: Optional message history for file context
        context: Optional page context (type, id, title)

    Returns:
        System prompt string
    """
    user_name = get_user_name(uid)

    # Get timezone and current datetime in user's timezone
    tz = notification_db.get_user_time_zone(uid)
    try:
        user_tz = ZoneInfo(tz)
        current_datetime_user = datetime.now(user_tz)
        current_datetime_str = current_datetime_user.strftime('%Y-%m-%d %H:%M:%S')
        current_datetime_iso = current_datetime_user.isoformat()
        print(f"🌍 _get_agentic_qa_prompt - User timezone: {tz}, Current time: {current_datetime_str}")
    except Exception:
        current_datetime_user = datetime.now(timezone.utc)
        current_datetime_str = current_datetime_user.strftime('%Y-%m-%d %H:%M:%S')
        current_datetime_iso = current_datetime_user.isoformat()
        tz = "UTC"
        print(f"🌍 _get_agentic_qa_prompt - User timezone: UTC (fallback), Current time: {current_datetime_str}")

    # Handle persona apps - they override the entire system prompt
    if app and app.is_a_persona():
        return app.persona_prompt or app.chat_prompt

    # Plugin-specific instructions for regular apps
    plugin_info = ""
    plugin_section = ""
    if app:
        plugin_info = f"Your name is: {app.name}, and your personality/description is '{app.description}'.\nMake sure to reflect your personality in your response."
        plugin_section = f"""<plugin_instructions>
{plugin_info}
</plugin_instructions>

"""

    # Add file context if messages contain files
    file_context_section = ""
    if messages:
        message_history_with_files = Message.get_messages_as_string(messages, include_file_info=True)
        if '[Files attached:' in message_history_with_files:
            file_context_section = f"""<file_context>
{message_history_with_files}
Use search_files_tool to reference file IDs shown above.
</file_context>

"""

    # Get user's current goal
    user_goal = goals_db.get_user_goal(uid)
    goal_section = ""
    if user_goal:
        goal_title = user_goal.get('title', '')
        goal_current = user_goal.get('current_value', 0)
        goal_target = user_goal.get('target_value', 0)
        goal_section = f"""<user_goal>
{user_name}'s goal: "{goal_title}" ({goal_current}/{goal_target})
</user_goal>

"""

    # Add page context if provided
    context_section = ""
    if context:
        # Sanitize title to prevent prompt injection (escape angle brackets and quotes)
        safe_title = (context.title or "").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        context_section = f"""<current_context>
{user_name} is currently viewing: {context.type} - "{safe_title}" (ID: {context.id or 'unknown'})
Keep this context in mind when answering their question.
</current_context>

"""

    base_prompt = f"""<assistant_role>
You are Omi, {user_name}'s AI mentor and advisor. Like a smart friend who actually pushes back.
Default: helpful, honest, and concise. Talk like a real person texting.
</assistant_role>

{goal_section}{file_context_section}{context_section}<current_datetime>
{user_name}'s timezone: {tz}
Now: {current_datetime_str} ({current_datetime_iso})
</current_datetime>

<mentor_behavior>
You're a MENTOR, not a yes-man. When you see a critical gap between {user_name}'s plan and their goal:

1. **Call it out directly** - Don't bury it after 5 paragraphs of summary
   - "Wait - you want 1M users but you're building for yourself. How does that connect?"
   - "You've said this 3 times but never done it. What's actually blocking you?"

2. **Only challenge when it MATTERS** - Not every message needs pushback
   - Challenge: strategy doesn't match goal, obvious better path exists, they're avoiding the hard thing
   - Don't challenge: small decisions, preferences, things that are fine either way

3. **Be direct like a cofounder would** - Real humans don't write essays
   - "honestly bro that doesn't make sense" > "I notice a potential misalignment between..."
   - "why not just do X?" > "Have you considered the alternative approach of X?"

4. **NEVER summarize what they just said** - They know what they said
   - Bad: "So you did X, Y, Z today and felt A, B, C..."
   - Good: Jump straight to your reaction/challenge/advice

5. **One clear recommendation** - Not 10 options or a menu
   - "Ship to production tonight. Everything else is noise until that's done."
</mentor_behavior>

<memory_priority>
CRITICAL: Before answering ANY question that could be in {user_name}'s memories
(numbers, counts, metrics, facts about people/companies/projects, "how many X", "how much Y"):

1. ALWAYS call get_memories_tool with limit=1000 FIRST
2. If memories contain an answer (especially numbers), use it directly
3. Only web search if: memories have nothing relevant AND it's current events
4. NEVER say "I couldn't find info" until you've checked memories
5. If memories and web conflict: tell user both, default trust memory for user-provided facts
</memory_priority>

<response_style>
Write like a real human texting - not an AI writing an essay.

Length:
- Default: 2-8 lines, conversational
- Reflections/planning: can be longer but NO SUMMARIES of what they said
- Quick replies: 1-3 lines

Format:
- NO bullet-point essays summarizing their message
- NO headers like "What you did:", "How you felt:", "Next steps:"
- NO "Great reflection!" or corporate praise
- Just talk normally like you're texting a friend who you respect
- Use lowercase, casual language when appropriate
</response_style>

<task_creation_rules>
ONLY create tasks when user explicitly asks: "add task", "create tasks for me", "remind me to"

When creating tasks:
- MAX 3-5 tasks, focus on what actually matters
- Keep descriptions SHORT (5-10 words)
- If their plan has gaps, challenge FIRST before creating tasks
- Don't create tasks for a strategy you think is wrong

NEVER create tasks when:
- User is reflecting/thinking out loud
- User asks a question
- You're giving advice
- You disagree with their plan
</task_creation_rules>

<citing_rules>
- Cite conversations at end of sentences: "You mentioned this[1][2]."
- NO SPACE before citation
- Don't cite irrelevant stuff
- No separate "References" section
</citing_rules>

<tool_instructions>
DateTime: Always ISO with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM). User times are in {tz}.
Current: {current_datetime_iso}

Tool priority:
1. **get_memories_tool (limit=1000)** - FIRST for any factual/numeric question
2. **vector_search_conversations_tool** - "What did I discuss about X"
3. **get_conversations_tool** - "What happened today/yesterday" (time-based)
4. **perplexity_search_tool** - ONLY for current events not in user data
5. **manage_daily_summary_tool** - Notification settings (enable/disable/time)
6. **create_action_item_tool** - ONLY when user explicitly asks for task creation

Datetime queries:
- "today" → {tz} 00:00:00 to 23:59:59
- "yesterday" → day before in {tz}
- "X hours ago" → that specific hour boundary
</tool_instructions>

<notification_controls>
User can manage notifications via chat. If user asks to enable/disable/change time:
- Identify notification type (currently: "reflection" / "daily summary")
- Call manage_daily_summary_tool
- Confirm in one line

Examples:
- "disable reflection notifications" → action="disable"
- "change reflection to 10pm" → action="set_time", hour=22
- "what time is my daily summary?" → action="get_settings"
</notification_controls>

<quality_control>
Before sending, ask yourself:
- Did I just summarize what they said? DELETE IT and add value instead
- Is there a critical gap in their plan? Call it out FIRST
- Am I writing like a robot or like a real person? Sound human
- Am I giving 10 tasks when 1-3 focused ones would be better?
- Skip "Here's", "Based on", "Great reflection!"
</quality_control>

<instructions>
- If their plan has a critical flaw vs their goal, lead with that challenge
- Talk like a smart friend, not an AI assistant
- Keep it real - lowercase is fine, be direct
- Check memories (limit=1000) before saying "I don't know"
- Convert times to {user_name}'s timezone ({tz})
- Only create tasks when explicitly requested AND you think the plan makes sense
{"- Reflect " + app.name + "'s personality" if app else ""}
</instructions>

{plugin_section}"""

    return base_prompt.strip()


def qa_rag(
    uid: str,
    question: str,
    context: str,
    plugin: Optional[App] = None,
    cited: Optional[bool] = False,
    messages: List[Message] = [],
    tz: Optional[str] = "UTC",
) -> str:
    prompt = _get_qa_rag_prompt(uid, question, context, plugin, cited, messages, tz)
    # print('qa_rag prompt', prompt)
    return llm_medium.invoke(prompt).content


def qa_rag_stream(
    uid: str,
    question: str,
    context: str,
    plugin: Optional[App] = None,
    cited: Optional[bool] = False,
    messages: List[Message] = [],
    tz: Optional[str] = "UTC",
    callbacks=[],
) -> str:
    prompt = _get_qa_rag_prompt(uid, question, context, plugin, cited, messages, tz)
    # print('qa_rag prompt', prompt)
    return llm_medium_stream.invoke(prompt, {'callbacks': callbacks}).content


# **************************************************
# ************* RETRIEVAL (EMOTIONAL) **************
# **************************************************


def retrieve_memory_context_params(uid: str, memory: Conversation) -> List[str]:
    person_ids = memory.get_person_ids()
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    transcript = memory.get_transcript(False, people=people)
    if len(transcript) == 0:
        return []

    prompt = f'''
    Based on the current transcript of a conversation.

    Your task is to extract the correct and most accurate context in the conversation, to be used to retrieve more information.
    Provide a list of topics in which the current conversation needs context about, in order to answer the most recent user request.

    Conversation:
    {transcript}
    '''.replace(
        '    ', ''
    ).strip()

    try:
        with_parser = llm_mini.with_structured_output(TopicsContext)
        response: TopicsContext = with_parser.invoke(prompt)
        return response.topics
    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return []


def obtain_emotional_message(uid: str, memory: Conversation, context: str, emotion: str) -> str:
    user_name, memories_str = get_prompt_memories(uid)

    person_ids = memory.get_person_ids()
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    transcript = memory.get_transcript(False, people=people)
    prompt = f"""
    You are a thoughtful and encouraging Friend.
    Your best friend is {user_name}, {memories_str}

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
    """.replace(
        '    ', ''
    ).strip()
    return llm_mini.invoke(prompt).content


# **********************************************
# ************* CHAT V2 LANGGRAPH **************
# **********************************************


class ExtractedInformation(BaseModel):
    people: List[str] = Field(
        default=[],
        examples=[['John Doe', 'Jane Doe']],
        description='Identify all the people names who were mentioned during the conversation.',
    )
    topics: List[str] = Field(
        default=[],
        examples=[['Artificial Intelligence', 'Machine Learning']],
        description='List all the main topics and subtopics that were discussed.',
    )
    entities: List[str] = Field(
        default=[],
        examples=[['OpenAI', 'GPT-4']],
        description='List any products, technologies, places, or other entities that are relevant to the conversation.',
    )
    dates: List[str] = Field(
        default=[],
        examples=[['2024-01-01', '2024-01-02']],
        description=f'Extract any dates mentioned in the conversation. Use the format YYYY-MM-DD.',
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
    print("extract_question_from_conversation")
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

    **IMPORTANT**: If the user gives a command or imperative statement (like "remind me to...", "add task to...", "create action item..."), \
    convert it to a question format by adding "Can you" or "Could you" at the beginning. \
    Examples:
    - "remind me to buy milk tomorrow" -> "Can you remind me to buy milk tomorrow"
    - "add task to finish report" -> "Can you add task to finish report"
    - "create action item for meeting" -> "Can you create action item for meeting"

    You MUST keep the original <date_in_term>

    Output a WH-question or a question that starts with "Can you" or "Could you" for commands.

    Example 1:
    <user_last_messages>
    <message>
        <sender>User</sender>
        <content>
            According to WHOOP, my HRV this Sunday was the highest it's been in a month. Here's what I did:

            Attended an outdoor party (cold weather, talked a lot more than usual).
            Smoked weed (unusual for me).
            Drank lots of relaxing tea.

            Can you prioritize each activity on a 0-10 scale for how much it might have influenced my HRV?
        </content>
    </message>
    </user_last_messages>
    Expected output: "How should each activity (going to a party and talking a lot, smoking weed, and drinking lots of relaxing tea) be prioritized on a scale of 0-10 in terms of their impact on my HRV, considering the recent activities that led to the highest HRV this month?"

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
    '''.replace(
        '    ', ''
    ).strip()
    # print(prompt)
    question = llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question
    # print(question)
    return question


def retrieve_metadata_fields_from_transcript(
    uid: str, created_at: datetime, transcript_segment: List[dict], tz: str, photos: List[ConversationPhoto] = None
) -> ExtractedInformation:
    context_parts = []
    if transcript_segment:
        transcript = ''
        for segment in transcript_segment:
            transcript += f'{segment["text"].strip()}\n\n'
        if transcript.strip():
            context_parts.append(f"Conversation Transcript:\n```\n{transcript.strip()}\n```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos, include_timestamps=True)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    if not context_parts:
        return {'people': [], 'topics': [], 'entities': [], 'dates': []}

    full_context = "\n\n".join(context_parts)

    # TODO: ask it to use max 2 words? to have more standardization possibilities
    prompt = f'''
    You will be given content which could be a raw transcript of a conversation, a series of photo descriptions from a wearable camera, or both. The transcript has about 20% word error rate, and diarization is also made very poorly.

    Your task is to extract the most accurate information from the content in the output object indicated below.

    Make sure as a first step, you infer and fix any raw transcript errors and then proceed to extract the information from the entire content.

    For context when extracting dates, today is {created_at.astimezone(timezone.utc).strftime('%Y-%m-%d')} in UTC. {tz} is the user's timezone, convert it to UTC and respond in UTC.
    If one says "today", it means the current day.
    If one says "tomorrow", it means the next day after today.
    If one says "yesterday", it means the day before today.
    If one says "next week", it means the next monday.
    Do not include dates greater than 2025.

    Content:
    ```
    {full_context}
    ```
    '''.replace(
        '    ', ''
    )
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
        'dates': [],
    }
    # 'dates': [date.strftime('%Y-%m-%d') for date in result.dates],
    for date in result.dates:
        try:
            date = datetime.strptime(date, '%Y-%m-%d')
            # if date.year > 2025:
            #    continue
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


def retrieve_metadata_from_message(
    uid: str, created_at: datetime, message_text: str, tz: str, source_spec: str = None
) -> ExtractedInformation:
    """Extract metadata from messaging app content"""
    source_context = f"from {source_spec}" if source_spec else "from a messaging application"

    prompt = f'''
    You will be given the content of a message or conversation {source_context}.

    Your task is to extract the most accurate information from the message in the output object indicated below.

    Focus on identifying:
    1. People mentioned in the message (sender, recipients, and anyone referenced)
    2. Topics discussed in the message
    3. Organizations, products, locations, or other entities mentioned
    4. Any dates or time references

    For context when extracting dates, today is {created_at.astimezone(timezone.utc).strftime('%Y-%m-%d')} in UTC. 
    {tz} is the user's timezone, convert it to UTC and respond in UTC.
    If the message mentions "today", it means the current day.
    If the message mentions "tomorrow", it means the next day after today.
    If the message mentions "yesterday", it means the day before today.
    If the message mentions "next week", it means the next monday.
    Do not include dates greater than 2025.

    Message Content:
    ```
    {message_text}
    ```
    '''.replace(
        '    ', ''
    )

    return _process_extracted_metadata(uid, prompt)


def retrieve_metadata_from_text(
    uid: str, created_at: datetime, text: str, tz: str, source_spec: str = None
) -> ExtractedInformation:
    """Extract metadata from generic text content"""
    source_context = f"from {source_spec}" if source_spec else "from a text document"

    prompt = f'''
    You will be given the content of a text {source_context}.

    Your task is to extract the most accurate information from the text in the output object indicated below.

    Focus on identifying:
    1. People mentioned in the text (author, recipients, and anyone referenced)
    2. Topics discussed in the text
    3. Organizations, products, locations, or other entities mentioned
    4. Any dates or time references

    For context when extracting dates, today is {created_at.astimezone(timezone.utc).strftime('%Y-%m-%d')} in UTC. 
    {tz} is the user's timezone, convert it to UTC and respond in UTC.
    If the text mentions "today", it means the current day.
    If the text mentions "tomorrow", it means the next day after today.
    If the text mentions "yesterday", it means the day before today.
    If the text mentions "next week", it means the next monday.
    Do not include dates greater than 2025.

    Text Content:
    ```
    {text}
    ```
    '''.replace(
        '    ', ''
    )

    return _process_extracted_metadata(uid, prompt)


def _process_extracted_metadata(uid: str, prompt: str) -> dict:
    """Process the extracted metadata from any source"""
    try:
        result: ExtractedInformation = llm_mini.with_structured_output(ExtractedInformation).invoke(prompt)
    except Exception as e:
        print(f'Error extracting metadata: {e}')
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
        'entities': [normalize_filter(e) for e in result.entities],
        'dates': [],
    }

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

    The JSON below contains samples of available filters as suggestions, but you are not limited to only these options. 
    However, you must choose from the ones that are actually available in the provided lists.
    Find as many as possible that can relate to the question asked, prioritizing the most relevant ones.
    ```
    {json.dumps(filters_available, indent=2)}
    ```

    Question: {question}
    '''.replace(
        '    ', ''
    ).strip()
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
    user_name, memories_str = get_prompt_memories(uid)

    person_ids = list(set(segment.person_id for segment in segments if segment.person_id))
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    prompt = f'''
    {user_name} is having a conversation.

    This is what you know about {user_name}: {memories_str}

    You will be the transcript of a recent conversation between {user_name} and a few people, \
    your task is to understand the last few exchanges, and identify in order to provide advice to {user_name}, what other things about {user_name} \
    you should know.

    For example, if the conversation is about a new job, you should output a question like "What discussions have I had about job search?".
    For example, if the conversation is about a new programming languages, you should output a question like "What have I chatted about programming?".

    Make sure as a first step, you infer and fix the raw transcript errors and then proceed to figure out the most meaningful question to ask.

    You must output at WH-question, that is, a question that starts with a WH-word, like "What", "When", "Where", "Who", "Why", "How".

    Conversation:
    ```
    {TranscriptSegment.segments_as_string(segments, people=people)}
    ```
    '''.replace(
        '    ', ''
    ).strip()
    return llm_mini.with_structured_output(OutputQuestion).invoke(prompt).question


class OutputMessage(BaseModel):
    message: str = Field(description='The message to be sent to the user.', max_length=200)


def provide_advice_message(uid: str, segments: List[TranscriptSegment], context: str) -> str:
    user_name, memories_str = get_prompt_memories(uid)

    person_ids = [s.person_id for s in segments if s.person_id]
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    transcript = TranscriptSegment.segments_as_string(segments, people=people)
    # TODO: tweak with different type of requests, like this, or roast, or praise or emotional, etc.

    prompt = f"""
    You are a brutally honest, very creative, sometimes funny, indefatigable personal life coach who helps people improve their own agency in life, \
    pulling in pop culture references and inspirational business and life figures from recent history, mixed in with references to recent personal memories,
    to help drive the point across.

    {memories_str}

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
    """.replace(
        '    ', ''
    ).strip()
    return llm_mini.with_structured_output(OutputMessage).invoke(prompt).message
