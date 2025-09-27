from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from .clients import llm_mini, llm_mini_stream, llm_medium_stream, llm_medium
from database.vector_db_convos import search_conversation_context, get_conversation_summary_for_chat
from models.chat_convo import ConversationChatMessage
from utils.llms.memory import get_prompt_memories


# ****************************************
# ************* CONVERSATION CHAT ********
# ****************************************


class ConversationQuestion(BaseModel):
    question: str = Field(description='The extracted user question about the conversation.')


def extract_question_from_conversation_messages(messages: List[ConversationChatMessage]) -> str:
    """Extract the user's question from recent conversation chat messages"""
    print("extract_question_from_conversation_messages")

    # Find the last user message
    user_message_idx = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].sender == 'ai':
            break
        if messages[i].sender == 'human':
            user_message_idx = i

    user_last_messages = messages[user_message_idx:]
    if len(user_last_messages) == 0:
        return ""

    prompt = f'''
    You will be given recent messages from a conversation-specific chat where a user is asking questions about a particular conversation.
    
    Your task is to identify the question the user is asking about this conversation.
    
    If the user is not asking a question (e.g., just saying "Hi", "Hello", "Thanks"), respond with an empty string.
    
    If the user is asking a question, extract and rephrase it as a clear, complete question about the conversation.
    
    Examples:
    - "What did we talk about?" → "What topics were discussed in this conversation?"
    - "Any action items from this?" → "What action items were generated from this conversation?"
    - "Who was speaking?" → "Who were the participants in this conversation?"
    - "What was decided?" → "What decisions were made in this conversation?"
    
    Recent messages:
    {ConversationChatMessage.get_messages_as_xml(user_last_messages)}
    
    Previous context (for reference):
    {ConversationChatMessage.get_messages_as_xml(messages)}
    '''.replace(
        '    ', ''
    ).strip()

    question = llm_mini.with_structured_output(ConversationQuestion).invoke(prompt).question
    print(f"Extracted question: {question}")
    return question


class RequiresContext(BaseModel):
    value: bool = Field(description="Whether the question requires conversation context to answer")


def question_requires_conversation_context(question: str) -> bool:
    """Determine if the question needs conversation context or can be answered generally"""
    if not question.strip():
        return False

    prompt = f'''
    Based on the user's question about a conversation, determine if this requires specific context from that conversation to answer properly.
    
    Examples requiring context:
    - "What did we discuss?" → True
    - "Who was in this conversation?" → True  
    - "What action items were created?" → True
    - "What was the main topic?" → True
    
    Examples NOT requiring context:
    - "Hi" → False
    - "How are you?" → False
    - "Thank you" → False
    - "What is artificial intelligence?" (general question) → False
    
    User's Question: {question}
    '''

    with_parser = llm_mini.with_structured_output(RequiresContext)
    response: RequiresContext = with_parser.invoke(prompt)
    return response.value


def get_simple_conversation_response_prompt(
    uid: str, messages: List[ConversationChatMessage], conversation_id: str
) -> str:
    """Generate prompt for simple conversation responses that don't need context"""

    user_name, memories_str = get_prompt_memories(uid)  # Same as main chat
    conversation_history = ConversationChatMessage.get_messages_as_string(messages)
    conversation_summary = get_conversation_summary_for_chat(uid, conversation_id)

    return f"""
    You are a helpful assistant for {user_name} discussing a specific conversation.
    
    About {user_name}: {memories_str}
    
    You are currently in a chat about this conversation: {conversation_summary}
    
    Respond naturally and helpfully. If the user asks about specific details from the conversation that you don't have context for, let them know you'd be happy to help but need to search through the conversation content.
    
    Chat History:
    {conversation_history}
    
    Response:
    """.replace(
        '    ', ''
    ).strip()


def answer_simple_conversation_message(uid: str, messages: List[ConversationChatMessage], conversation_id: str) -> str:
    """Generate a simple response without conversation context"""
    prompt = get_simple_conversation_response_prompt(uid, messages, conversation_id)
    return llm_mini.invoke(prompt).content


def answer_simple_conversation_message_stream(
    uid: str, messages: List[ConversationChatMessage], conversation_id: str, callbacks=[]
) -> str:
    """Generate a simple streaming response without conversation context"""
    prompt = get_simple_conversation_response_prompt(uid, messages, conversation_id)
    return llm_mini_stream.invoke(prompt, {'callbacks': callbacks}).content


def get_conversation_qa_prompt(
    uid: str,
    question: str,
    conversation_context: str,
    messages: List[ConversationChatMessage],
    conversation_title: str,
    conversation_id: str,
) -> str:
    """Generate prompt for conversation-specific Q&A with context"""

    user_name, memories_str = get_prompt_memories(uid)  # Same as main chat
    memories_str = '\n'.join(memories_str.split('\n')[1:]).strip()  # Same processing as main chat
    messages_history = ConversationChatMessage.get_messages_as_xml(messages)

    return (
        f"""
    <assistant_role>
        You are an assistant helping {user_name} understand and analyze a specific conversation.
    </assistant_role>

    <task>
        Answer the user's question about the conversation titled "{conversation_title}" using the provided conversation context.
    </task>

    <instructions>
        - Use the conversation context (transcript, summary, memories, action items) to answer the question accurately
        - Be specific and cite relevant parts of the conversation when possible
        - If asked about participants, refer to speakers by their identifiers (Speaker 0, Speaker 1, etc.) or names if provided
        - For action items, include completion status and due dates if available
        - If the question cannot be answered from the available context, be honest about limitations
        - Keep responses conversational and helpful
        - You can reference line numbers, timestamps, or specific quotes from the transcript when relevant
    </instructions>

    <user_facts>
        [Use the following User Facts if relevant to the conversation analysis]
        {memories_str.strip()}
    </user_facts>

    <conversation_context>
        {conversation_context}
    </conversation_context>

    <question>
        {question}
    </question>

    <chat_history>
        {messages_history}
    </chat_history>

    <current_datetime>
        Current date time in UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
    </current_datetime>

    <answer>
    """.replace(
            '    ', ''
        )
        .replace('\n\n\n', '\n\n')
        .strip()
    )


def answer_conversation_question(
    uid: str,
    question: str,
    conversation_context: str,
    messages: List[ConversationChatMessage],
    conversation_title: str,
    conversation_id: str,
) -> str:
    """Answer a question about a conversation using context"""

    prompt = get_conversation_qa_prompt(
        uid, question, conversation_context, messages, conversation_title, conversation_id
    )
    return llm_medium.invoke(prompt).content


def answer_conversation_question_stream(
    uid: str,
    question: str,
    conversation_context: str,
    messages: List[ConversationChatMessage],
    conversation_title: str,
    conversation_id: str,
    callbacks=[],
) -> str:
    """Answer a question about a conversation using context with streaming"""

    prompt = get_conversation_qa_prompt(
        uid, question, conversation_context, messages, conversation_title, conversation_id
    )
    return llm_medium_stream.invoke(prompt, {'callbacks': callbacks}).content


def get_conversation_context_for_question(uid: str, conversation_id: str, question: str) -> dict:
    """Get relevant context from a conversation for answering a question"""

    # For conversation chats, we always return the full context since it's scoped to one conversation
    # Future enhancement: could filter context based on question topic
    context = search_conversation_context(
        uid=uid, conversation_id=conversation_id, query=question, include_memories=True, include_action_items=True
    )

    return context


# ************************************************
# ************* CONVERSATION ANALYSIS ************
# ************************************************


def analyze_conversation_for_insights(uid: str, conversation_id: str) -> str:
    """Generate insights and analysis about a conversation"""

    context = search_conversation_context(uid, conversation_id)
    user_name, memories_str = get_prompt_memories(uid)  # Same as main chat

    prompt = f"""
    As an AI assistant for {user_name}, analyze this conversation and provide helpful insights.
    
    About {user_name}: {memories_str}
    
    Conversation Content:
    {context['context_text']}
    
    Please provide:
    1. Key topics discussed
    2. Important decisions made
    3. Action items and next steps
    4. Notable quotes or insights
    5. Overall conversation summary
    
    Keep the analysis concise and actionable.
    """

    return llm_medium.invoke(prompt).content


# TODO: Future Enhancement - Dynamic Suggestions
# def suggest_follow_up_questions(uid: str, conversation_id: str) -> List[str]:
#     """
#     Future: Make suggestions dynamic based on chat history progression
#     - Include recent chat messages to avoid repeated questions
#     - Generate contextual suggestions based on chat evolution
#     - Avoid suggesting topics already discussed
#     """


def suggest_follow_up_questions(uid: str, conversation_id: str) -> List[str]:
    """Suggest follow-up questions the user might want to ask about the conversation"""

    context = search_conversation_context(uid, conversation_id)

    prompt = f"""
    Based on this conversation content, suggest 3-5 relevant follow-up questions that someone might want to ask to better understand the conversation.
    
    Conversation Content:
    {context['context_text'][:1000]}...  
    
    Format as a simple list of questions, one per line.
    Focus on actionable questions about decisions, action items, key points, or participants.
    
    Example format:
    - What were the main decisions made in this conversation?
    - Who was responsible for the action items?
    - What are the next steps discussed?
    """

    response = llm_mini.invoke(prompt).content
    # Parse the response into a list
    questions = [q.strip('- ').strip() for q in response.split('\n') if q.strip() and q.strip().startswith('- ')]
    return questions[:5]  # Return max 5 questions
