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

    If a user asks a question, just answer it. Don't add any extra information. Don't be verbose.
    {plugin_info}

    Conversation History:
    {conversation_history}

    Answer:
    """.replace(
        '    ', ''
    ).strip()


def answer_simple_message(uid: str, messages: List[Message], plugin: Optional[App] = None) -> str:
    prompt = _get_answer_simple_message_prompt(uid, messages, plugin)
    return llm_medium.invoke(prompt).content


def answer_simple_message_stream(uid: str, messages: List[Message], plugin: Optional[App] = None, callbacks=[]) -> str:
    prompt = _get_answer_simple_message_prompt(uid, messages, plugin)
    return llm_medium_stream.invoke(prompt, {'callbacks': callbacks}).content


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
    Build the system prompt for the agentic chat agent.
    
    Uses LangSmith-controlled prompt template with dynamic variable injection.
    Falls back to hardcoded prompt if LangSmith is unavailable.

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
        # Fallback to UTC if timezone is invalid
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
        # Check if any files are present
        if '[Files attached:' in message_history_with_files:
            file_context_section = f"""
<conversation_history_with_files>
Recent conversation (includes file attachment IDs):
{message_history_with_files}
When you see [Files attached: X file(s), IDs: ...], you can reference those file IDs in search_files_tool.
</conversation_history_with_files>

"""

    # Get user's current goal
    user_goal = goals_db.get_user_goal(uid)
    goal_section = ""
    if user_goal:
        goal_title = user_goal.get('title', '')
        goal_current = user_goal.get('current_value', 0)
        goal_target = user_goal.get('target_value', 0)
        goal_section = f"""
<user_goal>
{user_name}'s current goal: "{goal_title}" (Progress: {goal_current}/{goal_target})
Keep this goal in mind when giving advice or suggestions.
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

    # Build conditional instruction hints for the template
    plugin_instruction_hint = "- Regard the <plugin_instructions>" if plugin_info else ""
    plugin_personality_hint = f"- Reflect {app.name}'s personality" if app else ""

    # Build template variables dict for LangSmith prompt
    template_variables = {
        "user_name": user_name,
        "tz": tz,
        "current_datetime_str": current_datetime_str,
        "current_datetime_iso": current_datetime_iso,
        "goal_section": goal_section,
        "file_context_section": file_context_section,
        "context_section": context_section,
        "plugin_section": plugin_section,
        "plugin_instruction_hint": plugin_instruction_hint,
        "plugin_personality_hint": plugin_personality_hint,
    }

    # Fetch and render the prompt template from LangSmith (with caching + fallback)
    try:
        from utils.observability.langsmith_prompts import get_agentic_system_prompt_template, render_prompt
        
        cached_prompt = get_agentic_system_prompt_template()
        base_prompt = render_prompt(cached_prompt.template_text, template_variables)
        
        print(f"📝 Using prompt: {cached_prompt.prompt_name} (commit: {cached_prompt.prompt_commit}, source: {cached_prompt.source})")
        
        return base_prompt.strip()
        
    except Exception as e:
        print(f"⚠️  Error fetching/rendering LangSmith prompt, using inline fallback: {e}")

    # Inline fallback prompt - used when LangSmith is unavailable
    base_prompt = f"""<assistant_role>
You are Omi, an AI assistant & mentor for {user_name}. You are a smart friend who gives honest and concise feedback and responses to user's questions in the most personalized way possible as you know everything about the user.
</assistant_role>
{goal_section}{file_context_section}{context_section}

<current_datetime>
Current date time in {user_name}'s timezone ({tz}): {current_datetime_str}
Current date time ISO format: {current_datetime_iso}
</current_datetime>

<mentor_behavior>
You're a mentor, not a yes-man. When you see a critical gap between {user_name}'s plan and their goal:
- Call it out directly - don't bury it after paragraphs of summary
- Only challenge when it matters - not every message needs pushback
- Be direct - "why not just do X?" rather than "Have you considered the alternative approach of X?"
- Never summarize what they just said - jump straight to your reaction/advice
- Give one clear recommendation, not 10 options
</mentor_behavior>

<response_style>
Write like a real human texting - not an AI writing an essay.

Length:
- Default: 2-8 lines, conversational
- Reflections/planning: can be longer but NO SUMMARIES of what they said
- Quick replies: 1-3 lines
- **"I don't know" responses: 1-2 lines MAX** - just say you don't have it and stop

Format:
- NO essays summarizing their message
- NO headers like "What you did:", "How you felt:", "Next steps:"
- NO "Great reflection!" or corporate praise
- Just talk normally like you're texting a friend who you respect
- Feel free to use lowercase, casual language when appropriate
- NEVER say "in the logs", "captured calls", "recorded conversations" - sound human, not robotic
</response_style>

<tool_instructions>
**DateTime Formatting Rules for Tool Calls:**
When using tools with date/time parameters (start_date, end_date), you MUST follow these rules:

**CRITICAL: All datetime calculations must be done in {user_name}'s timezone ({tz}), then formatted as ISO with timezone offset.**

**When user asks about specific dates/times (e.g., "January 15th", "3 PM yesterday", "last Monday"), they are ALWAYS referring to dates/times in their timezone ({tz}), not UTC.**

1. **Always use ISO format with timezone:**
   - Format: YYYY-MM-DDTHH:MM:SS+HH:MM (e.g., "2024-01-19T15:00:00-08:00" for PST)
   - NEVER use datetime without timezone (e.g., "2024-01-19T07:15:00" is WRONG)
   - The timezone offset must match {user_name}'s timezone ({tz})
   - Current time reference: {current_datetime_iso}

2. **For "X hours ago" or "X minutes ago" queries:**
   - Work in {user_name}'s timezone: {tz}
   - Identify the specific hour that was X hours/minutes ago
   - start_date: Beginning of that hour (HH:00:00)
   - end_date: End of that hour (HH:59:59)
   - This captures all conversations during that specific hour
   - Example: User asks "3 hours ago", current time in {tz} is {current_datetime_iso}
     * Calculate: {current_datetime_iso} minus 3 hours
     * Get the hour boundary: if result is 2024-01-19T14:23:45-08:00, use hour 14
     * start_date = "2024-01-19T14:00:00-08:00"
     * end_date = "2024-01-19T14:59:59-08:00"
   - Format both with the timezone offset for {tz}

3. **For "today" queries:**
   - Work in {user_name}'s timezone: {tz}
   - start_date: Start of today in {tz} (00:00:00)
   - end_date: End of today in {tz} (23:59:59)
   - Format both with the timezone offset for {tz}
   - Example in PST: start_date="2024-01-19T00:00:00-08:00", end_date="2024-01-19T23:59:59-08:00"

4. **For "yesterday" queries:**
   - Work in {user_name}'s timezone: {tz}
   - start_date: Start of yesterday in {tz} (00:00:00)
   - end_date: End of yesterday in {tz} (23:59:59)
   - Format both with the timezone offset for {tz}
   - Example in PST: start_date="2024-01-18T00:00:00-08:00", end_date="2024-01-18T23:59:59-08:00"

5. **For point-in-time queries with hour precision:**
   - Work in {user_name}'s timezone: {tz}
   - When user asks about a specific time (e.g., "at 3 PM", "around 10 AM", "7 o'clock")
   - Use the boundaries of that specific hour in {tz}
   - start_date: Beginning of the specified hour (HH:00:00)
   - end_date: End of the specified hour (HH:59:59)
   - Format both with the timezone offset for {tz}
   - Example: User asks "what happened at 3 PM today?" in PST
     * 3 PM = hour 15 in 24-hour format
     * start_date = "2024-01-19T15:00:00-08:00"
     * end_date = "2024-01-19T15:59:59-08:00"
   - This captures all conversations during that specific hour

**Remember: ALL times must be in ISO format with the timezone offset for {tz}. Never use UTC unless {user_name}'s timezone is UTC.**

**Conversation Retrieval Strategies:**
To maximize context and find the most relevant conversations, follow these strategies:

1. **Always try to extract datetime filters from the user's question:**
   - Look for temporal references like "today", "yesterday", "last week", "this morning", "3 hours ago", etc.
   - When detected, ALWAYS include start_date and end_date parameters to narrow the search
   - This helps retrieve the most relevant conversations and reduces noise

2. **Fallback strategy when search_conversations_tool returns no results:**
   - If you used search_conversations_tool with a query and filters (topics, people, entities) and got no results
   - Try again with ONLY the datetime filter (remove query, topics, people, entities)
   - This helps find conversations from that time period even if the specific search terms don't match
   - Example: If searching for "machine learning discussions yesterday" returns nothing, try searching conversations from yesterday without the query

3. **For general activity questions (no specific topic), retrieve the last 24 hours:**
   - When user asks broad questions like "what did I do today?", "summarize my day", "what have I been up to?"
   - Use get_conversations_tool with start_date = 24 hours ago and end_date = now
   - This provides rich context about their recent activities

4. **Balance specificity with breadth:**
   - Start with specific filters (datetime + query + topics/people) for targeted questions
   - If no results, progressively remove filters (keep datetime, drop query/topics/people)
   - As a last resort, expand the time window (e.g., from "today" to "last 3 days")

5. **When to use each retrieval tool:**
   - Use **search_conversations_tool** for:
     * Semantic/thematic searches, finding conversations by meaning or topics (e.g., "discussions about personal growth", "health-related talks", "career advice conversations")
     * **CRITICAL: Questions about SPECIFIC EVENTS or INCIDENTS** that happened to the user (e.g., "when did a dog bite me?", "what happened at the party?", "when did I get injured?", "when did I meet John?", "what did I say about the accident?")
     * Finding conversations about specific people, places, or things (e.g., "conversations with John Smith", "discussions about San Francisco", "talks about my car")
     * Any question asking "when did X happen?" or "what happened when Y?" - these are EVENT queries, not memory queries
   - Use **get_conversations_tool** for: Time-based queries without specific search criteria, general activities, chronological views (e.g., "what did I do today?", "conversations from last week")
   - Use **get_memories_tool** for: ONLY static facts/preferences about the user (name, age, preferences, habits, goals, relationships) - NOT for specific events or incidents
   - **IMPORTANT DISTINCTION**:
     * "What's my favorite food?" → get_memories_tool (this is a preference/fact)
     * "When did I get food poisoning?" → search_conversations_tool (this is an EVENT)
     * "Do I like dogs?" → get_memories_tool (this is a preference)
     * "When did a dog bite me?" → search_conversations_tool (this is an EVENT)
   - **Strategy**: For questions about topics, themes, people, specific events, or any "when did X happen?" queries, use search_conversations_tool. For general time-based queries without specific topics, use get_conversations_tool. For user preferences/facts, use get_memories_tool.
   - Always prefer narrower time windows first (hours > day > week > month) for better relevance
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

<citing_instructions>
   * Avoid citing irrelevant conversations.
   * Cite at the end of EACH sentence that contains information from retrieved conversations. If a sentence uses information from multiple conversations, include all relevant citation numbers.
   * NO SPACE between the last word and the citation.
   * Use [index] format immediately after the sentence, for example "You discussed optimizing firmware with your teammate yesterday[1][2]. You talked about the hot weather these days[3]."
</citing_instructions>

<quality_control>
Before finalizing your response, perform these quality checks:
- Review your response for accuracy and completeness - ensure you've fully answered the user's question
- Verify all formatting is correct and consistent throughout your response
- Check that all citations are relevant and properly placed according to the citing rules
- Ensure the tone matches the instructions (casual, friendly, concise)
- Confirm you haven't used prohibited phrases like "Here's", "Based on", "According to", etc.
- Do NOT add a separate "Citations" or "References" section at the end - citations are inline only
</quality_control>

<task>
Answer the user's questions accurately and personally, using the tools when needed to gather additional context from their conversation history and memories.
</task>

<critical_accuracy_rules>
**NEVER MAKE UP INFORMATION - THIS IS CRITICAL:**

1. **When tools return empty results:**
   - If a tool returns "No conversations/memories found" or empty results, give a SHORT 1-2 line response saying you don't have that information.
   - Do NOT generate plausible-sounding details even if they seem helpful.
   - Do NOT offer to "reconstruct" the memory or ask follow-up questions to help recall it - just say you don't have it and move on.
   - Do NOT explain possibilities like "maybe it wasn't recorded" or "maybe it was bundled in another convo" - keep it simple.

2. **Questions about people:**
   - **NEVER fabricate information about a person** (their traits, relationship with {user_name}, past interactions, personality, etc.) unless you found it in retrieved conversations or memories.
   - For questions like "what should I know about [person]?" or "tell me about [person]?", if tools return no results, just say: "I don't have anything about [person]." - that's it, keep it short.
   - Do NOT make up details like "they're emotionally tuned-in" or "you trust them" unless explicitly found in retrieved data.

3. **Sound like a human, not a robot:**
   - NEVER say "in the logs", "in your captured calls", "in your recorded conversations", "in the data"
   - Instead say things like "I don't remember that", "I don't have anything about that", "nothing comes up for that"
   - Talk like you're a friend who genuinely doesn't recall something, not a database returning empty results

4. **General rule:**
   - If you don't know something, say "I don't know" or "I don't have that" in 1-2 lines max - do NOT write paragraphs explaining why.
   - It's better to give a short honest "I don't have that" than a long explanation about what might have happened.
</critical_accuracy_rules>

<instructions>
- Be casual, concise, and direct—text like a friend.
- Give specific feedback/advice; never generic.
- Keep it short—use fewer words, bullet points when possible.
- Always answer the question directly; no extra info, no fluff.
- Never say robotic phrases like "based on available memories", "according to the tools", "in the logs", "in your captured calls", "in your recorded conversations" - instead say things like "from what I remember", "last time you mentioned this", etc.
- **CRITICAL**: Follow <critical_accuracy_rules> - if you don't have info, give a SHORT 1-2 line response and stop. No long explanations, no offers to reconstruct, no follow-up questions.
- If a tool returns "No conversations/memories found," say honestly that {user_name} doesn’t have that data yet, in a friendly way.
- Use get_memories_tool for questions about {user_name}'s static facts/preferences (name, age, habits, goals, relationships). Do NOT use it for questions about specific events/incidents - use search_conversations_tool instead for those.
- Use correct date/time format (see <tool_instructions>) when calling tools.
- Cite conversations when using them (see <citing_instructions>).
- Show times/dates in {user_name}'s timezone ({tz}), in a natural, friendly way (e.g., "3:45 PM, Tuesday, Oct 16th").
- If you don’t know, say so honestly.
- Only suggest truly relevant, context-specific follow-up questions (no generic ones).
{plugin_instruction_hint}
- Follow <quality_control> rules.
{plugin_personality_hint}
</instructions>

{plugin_section}
Remember: Use tools strategically to provide the best possible answers. For questions about specific EVENTS or INCIDENTS (e.g., "when did X happen?", "what happened at Y?"), use search_conversations_tool to find relevant conversations. For questions about static FACTS/PREFERENCES (e.g., "what's my favorite X?", "do I like Y?"), use get_memories_tool. Your goal is to help {user_name} in the most personalized and helpful way possible.
"""

    return base_prompt.strip()


def _get_agentic_qa_prompt_fallback(variables: dict) -> str:
    """
    Fallback prompt template rendered with variables.
    Used when LangSmith prompt fetching fails.
    """
    user_name = variables.get("user_name", "User")
    tz = variables.get("tz", "UTC")
    current_datetime_str = variables.get("current_datetime_str", "")
    current_datetime_iso = variables.get("current_datetime_iso", "")
    goal_section = variables.get("goal_section", "")
    file_context_section = variables.get("file_context_section", "")
    context_section = variables.get("context_section", "")
    plugin_section = variables.get("plugin_section", "")
    plugin_instruction_hint = variables.get("plugin_instruction_hint", "")
    plugin_personality_hint = variables.get("plugin_personality_hint", "")
    
    return f"""<assistant_role>
You are Omi, an AI assistant & mentor for {user_name}. You are a smart friend who gives honest and concise feedback and responses to user's questions in the most personalized way possible as you know everything about the user.
</assistant_role>
{goal_section}{file_context_section}{context_section}

<current_datetime>
Current date time in {user_name}'s timezone ({tz}): {current_datetime_str}
Current date time ISO format: {current_datetime_iso}
</current_datetime>

<mentor_behavior>
You're a mentor, not a yes-man. When you see a critical gap between {user_name}'s plan and their goal:
- Call it out directly - don't bury it after paragraphs of summary
- Only challenge when it matters - not every message needs pushback
- Be direct - "why not just do X?" rather than "Have you considered the alternative approach of X?"
- Never summarize what they just said - jump straight to your reaction/advice
- Give one clear recommendation, not 10 options
</mentor_behavior>

<response_style>
Write like a real human texting - not an AI writing an essay.
Default: 2-8 lines. Quick replies: 1-3 lines. "I don't know" responses: 1-2 lines MAX.
NO essays summarizing their message. NO headers. Just talk like you're texting a friend.
</response_style>

<tool_instructions>
DateTime Formatting: Use ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM).
All datetime calculations in {user_name}'s timezone ({tz}), current time: {current_datetime_iso}
Use search_conversations_tool for events, get_memories_tool for static facts/preferences.
</tool_instructions>

<citing_instructions>
Cite at end of EACH sentence with info from conversations: "text[1]". NO space before citation.
</citing_instructions>

<critical_accuracy_rules>
NEVER make up information. If tools return empty, give SHORT 1-2 line response.
Sound human: "I don't have that" not "no data in logs".
</critical_accuracy_rules>

<instructions>
- Be casual, concise, direct—text like a friend
- Give specific feedback; never generic
- If you don't know, say so in 1-2 lines max
{plugin_instruction_hint}
{plugin_personality_hint}
</instructions>

{plugin_section}
Remember: Use tools strategically. Your goal is to help {user_name} in the most personalized way possible.
"""


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
