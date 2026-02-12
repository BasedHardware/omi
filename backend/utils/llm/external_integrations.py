from datetime import datetime, timezone
from typing import List
import pytz
from langchain_core.prompts import ChatPromptTemplate
import database.users as users_db
from models.conversation import Structured, Conversation
from models.other import Person
from utils.llm.clients import parser, llm_mini, llm_medium_experiment
from utils.llm.usage_tracker import track_usage, Features
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

    {format_instructions}'''.replace('    ', '').strip()

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

    # Set created_at for action items if not already set
    for action_item in response.action_items or []:
        if action_item.created_at is None:
            action_item.created_at = datetime.now(timezone.utc)

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
      '''.replace('    ', '').strip()

    response = llm_mini.with_structured_output(Structured).invoke(prompt)

    # Set created_at for action items if not already set
    for action_item in response.action_items or []:
        if action_item.created_at is None:
            action_item.created_at = datetime.now(timezone.utc)

    return response


def get_conversation_summary(uid: str, memories: List[Conversation]) -> str:
    user_name, memories_str = get_prompt_memories(uid)

    all_person_ids = []
    for m in memories:
        all_person_ids.extend(m.get_person_ids())

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
    """.replace('    ', '').strip()
    # print(prompt)
    with track_usage(uid, Features.DAILY_SUMMARY):
        return llm_mini.invoke(prompt).content


def generate_comprehensive_daily_summary(
    uid: str, conversations: List[Conversation], date_str: str, start_date_utc=None, end_date_utc=None
) -> dict:
    """
    Generate a comprehensive daily summary with structured data for storage.

    Returns a dictionary matching the DailySummary model structure.
    """
    import json
    import uuid
    import database.action_items as action_items_db

    # Get user's timezone
    user_profile = users_db.get_user_profile(uid)
    user_tz_str = user_profile.get('time_zone', 'UTC')
    try:
        user_tz = pytz.timezone(user_tz_str)
    except Exception:
        user_tz = pytz.UTC

    user_name, memories_str = get_prompt_memories(uid)

    all_person_ids = []
    for m in conversations:
        all_person_ids.extend(m.get_person_ids())

    people = []
    people_names = []
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(all_person_ids)))
        people = [Person(**p) for p in people_data]
        people_names = [p.name for p in people if p.name]

    conversation_history = Conversation.conversations_to_string(conversations, people=people)

    # Calculate stats - exclude discarded conversations
    non_discarded = [c for c in conversations if not c.discarded]
    total_conversations = len(non_discarded)
    total_duration_minutes = sum(
        (c.finished_at - c.started_at).total_seconds() / 60 for c in non_discarded if c.finished_at and c.started_at
    )

    # Extract ALL locations from non-discarded conversations
    locations = []
    for c in non_discarded:
        if c.geolocation and c.geolocation.latitude and c.geolocation.longitude:
            # Convert UTC time to user's local timezone
            local_time = None
            if c.started_at:
                utc_time = c.started_at
                if utc_time.tzinfo is None:
                    utc_time = pytz.UTC.localize(utc_time)
                local_time = utc_time.astimezone(user_tz).strftime("%H:%M")
            locations.append(
                {
                    "latitude": c.geolocation.latitude,
                    "longitude": c.geolocation.longitude,
                    "address": c.geolocation.address,
                    "conversation_id": c.id,
                    "time": local_time,
                }
            )

    # Fetch actual action items from the database for this date range
    actual_action_items = []
    if start_date_utc and end_date_utc:
        db_action_items = action_items_db.get_action_items(uid, start_date=start_date_utc, end_date=end_date_utc)
        for item in db_action_items:
            actual_action_items.append(
                {
                    "description": item.get("description", ""),
                    "priority": "high" if item.get("completed") == False else "medium",
                    "completed": item.get("completed", False),
                    "source_conversation_id": item.get("conversation_id"),
                }
            )

    # Build conversation ID mapping for the LLM
    convo_id_map = {i + 1: c.id for i, c in enumerate(non_discarded)}

    prompt = f"""You are creating a daily summary for {user_name}. {memories_str}

Today's date: {date_str}
Conversations: {total_conversations}

Here are {user_name}'s conversations from today (numbered 1-{total_conversations}):
```
{conversation_history}
```

Generate a JSON response. ONLY include sections with genuinely useful content - skip sections entirely if data is thin or low quality.

{{
    "headline": "Catchy one-liner (max 8 words)",
    "overview": "2-3 snappy lines. Crisp, insightful, no fluff.",
    "day_emoji": "Single emoji",
    "highlights": [
        {{
            "topic": "Short topic name",
            "emoji": "🎯",
            "summary": "One crisp sentence.",
            "conversation_numbers": [1, 2]
        }}
    ],
    "unresolved_questions": [
        {{
            "question": "Short question that wasn't answered",
            "conversation_number": 1
        }}
    ],
    "decisions_made": [
        {{
            "decision": "Short decision or conclusion",
            "conversation_number": 1
        }}
    ],
    "knowledge_nuggets": [
        {{
            "insight": "Short interesting fact or tip learned",
            "conversation_number": 1
        }}
    ]
}}

RULES:
- highlights: Max 4. One sentence each.
- unresolved_questions: Max 3. Short, punchy questions only. Keep each question short and snappy, less than 15 words.
- decisions_made: Max 3. Concrete decisions only. Only add here if it is something that the user has decided on. Tasks or action items don't belong here. Keep each decision short and snappy, less than 15 words.
- knowledge_nuggets: Max 3. Genuinely interesting learnings. Learnings are new learnings for the user, not something they might have already known. Shouldn't be very generic, should be a very specific learning. Keep each learning short and snappy, less than 15 words.
- conversation_number: Reference which conversation (1-{total_conversations}) it came from.
- SKIP sections entirely if no quality content.
- Be snappy. No fluff. No corporate speak. Only include sections that are genuinely useful and relevant.

Respond with ONLY valid JSON. Do not include any other text or comments."""

    try:
        with track_usage(uid, Features.DAILY_SUMMARY):
            response = llm_medium_experiment.invoke(prompt).content
        # Clean up response - remove markdown if present
        response = response.strip()
        if response.startswith('```'):
            response = response.split('```')[1]
            if response.startswith('json'):
                response = response[4:]
        response = response.strip()

        # Try to repair common JSON issues from LLM
        import re

        response = re.sub(r':\s*\\"([^"]*)\\"', r': "\1"', response)
        response = response.replace('\\"', '"')

        summary_data = json.loads(response)

        # Helper to map conversation number to ID
        def get_convo_id(num):
            if num and isinstance(num, int) and num in convo_id_map:
                return convo_id_map[num]
            return None

        # Process highlights - map conversation_numbers to conversation_ids
        highlights = []
        for h in summary_data.get("highlights", []):
            convo_nums = h.get("conversation_numbers", [])
            convo_ids = [get_convo_id(n) for n in convo_nums if get_convo_id(n)]
            highlights.append(
                {
                    "topic": h.get("topic", ""),
                    "emoji": h.get("emoji", "💡"),
                    "summary": h.get("summary", ""),
                    "conversation_ids": convo_ids,
                }
            )

        # Process unresolved questions
        unresolved_questions = []
        for q in summary_data.get("unresolved_questions", []):
            unresolved_questions.append(
                {"question": q.get("question", ""), "conversation_id": get_convo_id(q.get("conversation_number"))}
            )

        # Process decisions made
        decisions_made = []
        for d in summary_data.get("decisions_made", []):
            decisions_made.append(
                {"decision": d.get("decision", ""), "conversation_id": get_convo_id(d.get("conversation_number"))}
            )

        # Process knowledge nuggets
        knowledge_nuggets = []
        for k in summary_data.get("knowledge_nuggets", []):
            knowledge_nuggets.append(
                {"insight": k.get("insight", ""), "conversation_id": get_convo_id(k.get("conversation_number"))}
            )

        # Build the complete summary object
        summary_id = str(uuid.uuid4())
        return {
            "id": summary_id,
            "date": date_str,
            "created_at": datetime.utcnow().isoformat(),
            "headline": summary_data.get("headline", "Your Day in Review"),
            "overview": summary_data.get("overview", ""),
            "day_emoji": summary_data.get("day_emoji", "📅"),
            "stats": {
                "total_conversations": total_conversations,
                "total_duration_minutes": int(total_duration_minutes),
                "action_items_count": len(actual_action_items),
            },
            "highlights": highlights,
            "action_items": actual_action_items,
            "unresolved_questions": unresolved_questions,
            "decisions_made": decisions_made,
            "knowledge_nuggets": knowledge_nuggets,
            "locations": locations,
        }
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM response as JSON: {e}")
        print(f"Response was: {response}")
        # Return a basic summary on parse failure
        return {
            "id": str(uuid.uuid4()),
            "date": date_str,
            "created_at": datetime.utcnow().isoformat(),
            "headline": "Your Day in Review",
            "overview": f"You had {total_conversations} conversations today.",
            "day_emoji": "📅",
            "stats": {
                "total_conversations": total_conversations,
                "total_duration_minutes": int(total_duration_minutes),
                "action_items_count": len(actual_action_items),
            },
            "highlights": [],
            "action_items": actual_action_items,
            "unresolved_questions": [],
            "decisions_made": [],
            "knowledge_nuggets": [],
            "locations": locations,
        }
