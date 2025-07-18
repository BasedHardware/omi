from datetime import datetime
from typing import List
from langchain_core.prompts import ChatPromptTemplate
import database.users as users_db
from models.conversation import Structured, Conversation
from models.other import Person
from utils.llm.clients import parser, llm_mini
from utils.llms.memory import get_prompt_memories


def get_message_structure(
    text: str, started_at: datetime, language_code: str, tz: str, text_source_spec: str = None
) -> Structured:
    prompt_text = '''
    You are an expert message analyzer. Your task is to analyze the message content and provide structure and clarity.
    The message language is {language_code}. Use the same language {language_code} for your response.

    For the title, create a concise title that captures the main topic of the message.
    For the overview, summarize the message with the main points discussed, make sure to capture the key information and important details.
    For the action items, include any tasks or actions that need to be taken based on the message.
    For the category, classify the message into one of the available categories.
    For Calendar Events, include any events or meetings mentioned in the message. For date context, this message was sent on {started_at}. {tz} is the user's timezone, convert it to UTC and respond in UTC.

    Message Content: ```{text}```
    Message Source: {text_source_spec}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_mini | parser

    response = chain.invoke(
        {
            'language_code': language_code,
            'started_at': started_at.isoformat(),
            'tz': tz,
            'text': text,
            'text_source_spec': text_source_spec if text_source_spec else 'Messaging App',
            'format_instructions': parser.get_format_instructions(),
        }
    )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False
    return response


def summarize_experience_text(text: str, text_source_spec: str = None) -> Structured:
    source_context = f"Source: {text_source_spec}" if text_source_spec else "their own experiences or thoughts"
    prompt = f'''The user sent a text of {source_context}, and wants to create a memory from it.
      For the title, use the main topic of the experience or thought.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.
      For the action items, include any tasks or actions that need to be taken based on the content.
      For Calendar Events, include any events or meetings mentioned in the content.

      Text: ```{text}```
      '''.replace(
        '    ', ''
    ).strip()
    return llm_mini.with_structured_output(Structured).invoke(prompt)


def get_conversation_summary(uid: str, memories: List[Conversation]) -> str:
    user_name, memories_str = get_prompt_memories(uid)

    all_person_ids = []
    for m in memories:
        all_person_ids.extend([s.person_id for s in m.transcript_segments if s.person_id])

    people = []
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
        people = [Person(**p) for p in people_data]

    conversation_history = Conversation.conversations_to_string(memories, people=people)

    prompt = f"""
    You are an experienced mentor, that helps people achieve their goals and improve their lives.
    You are advising {user_name} right now, {memories_str}

    The following are a list of {user_name}'s conversations from today, with the transcripts and a slight summary of each, that {user_name} had during his day.
    {user_name} wants to get a summary of the key action items {user_name} has to take based on today's conversations.

    Remember {user_name} is busy so this has to be very efficient and concise.
    Respond in at most 50 words.

    Output your response in plain text, without markdown. No newline character and only use numbers for the action items.
    ```
    ${conversation_history}
    ```
    """.replace(
        '    ', ''
    ).strip()
    # print(prompt)
    return llm_mini.invoke(prompt).content
