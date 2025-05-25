from datetime import datetime
from typing import List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.app import App
from models.conversation import Structured, Conversation, ActionItem, Event
from .clients import llm_mini, llm_medium_experiment, parser, llm_high


class DiscardConversation(BaseModel):
    discard: bool = Field(description="If the conversation should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def should_discard_conversation(transcript: str) -> bool:
    if len(transcript.split(' ')) > 100:
        return False

    custom_parser = PydanticOutputParser(pydantic_object=DiscardConversation) # Renamed to avoid conflict
    prompt = ChatPromptTemplate.from_messages([
        '''
    You will receive a transcript snippet. Length is never a reason to discard.

        Task
        Decide if the snippet should be saved as a memory.

        KEEP  → output:  discard = False
        DISCARD → output: discard = True

        KEEP (discard = False) if it contains any of the following:
        • a task, request, or action item
        • a decision, commitment, or plan
        • a question that requires follow-up
        • personal facts, preferences, or details likely useful later
        • an insight, summary, or key takeaway

        If none of these are present, DISCARD (discard = True).

        Return exactly one line:
        discard = <True|False>


    Transcript: ```{transcript}```

    {format_instructions}'''.replace('    ', '').strip()
    ])
    chain = prompt | llm_mini | custom_parser
    try:
        response: DiscardConversation = chain.invoke({
            'transcript': transcript.strip(),
            'format_instructions': custom_parser.get_format_instructions(),
        })
        return response.discard

    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return False


def get_transcript_structure(transcript: str, started_at: datetime, language_code: str, tz: str) -> Structured:
    prompt_text = '''You are an expert conversation analyzer. Your task is to analyze the conversation and provide structure and clarity to the recording transcription of a conversation.
    The conversation language is {language_code}. Use the same language {language_code} for your response.

    For the title, Write a clear, compelling headline (≤ 10 words) that captures the central topic and outcome. Use Title Case, avoid filler words, and include a key noun + verb where possible (e.g., "Team Finalizes Q2 Budget" or "Family Plans Weekend Road Trip")
    For the overview, condense the conversation into a summary with the main topics discussed, making sure to capture the key points and important details from the conversation.
    For the emoji, select a single emoji that vividly reflects the core subject, mood, or outcome of the conversation. Strive for an emoji that is specific and evocative, rather than generic (e.g., prefer 🎉 for a celebration over 👍 for general agreement, or 💡 for a new idea over 🧠 for general thought).

    For the action items, apply a strict filter and use the format below:  
    • Include **only** tasks that have  
      a) a clear owner (named speaker or implied "you"),  
      b) a concrete next step **and** timing cue (date, "tomorrow", "next week", etc.),  
      c) real importance (money, health/safety, hard deadline, or explicit stress if missed).  
    • Exclude vague or trivial remarks ("We should grab lunch sometime").  
    • Merge duplicates; order by due date → spoken urgency → alphabetical.  
    • Format each as a single bullet with its own emoji from the whitelist 📞 📝 🏥 🚗 💻 🛠️ 📦 📊 📚 🔧 ⚠️ ⏳ 🎯 🔋 🎓 📢 💡.

        Example format:  
        - 🗓️ **Submit Q2 budget**  • due 05/31  
        - 💻 **Update project repo**  • tomorrow  

    For the category, classify the conversation into one of the available categories.

    For Calendar Events, include a list of events extracted from the conversation that the user must have on their calendar. For date context, this conversation happened on {started_at}. {tz} is the user's timezone; convert all event times to UTC and respond in UTC.


    Transcript: ```{transcript}```

    {format_instructions}'''.replace('    ', '').strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_high | parser # parser is imported from .clients

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


def get_reprocess_transcript_structure(transcript: str, started_at: datetime, language_code: str, tz: str,
                                       title: str) -> Structured:
    prompt_text = '''You are an expert conversation analyzer. Your task is to analyze the conversation and provide structure and clarity to the recording transcription of a conversation.
    The conversation language is {language_code}. Use the same language {language_code} for your response.

    For the title, use ```{title}```, if it is empty, use the main topic of the conversation.
    For the overview, condense the conversation into a summary with the main topics discussed, making sure to capture the key points and important details from the conversation.
    For the emoji, select a single emoji that vividly reflects the core subject, mood, or outcome of the conversation. Strive for an emoji that is specific and evocative, rather than generic (e.g., prefer 🎉 for a celebration over 👍 for general agreement, or 💡 for a new idea over 🧠 for general thought).

    For the action items, apply a strict filter and use the format below:  
    • Include **only** tasks that have  
      a) a clear owner (named speaker or implied "you"),  
      b) a concrete next step **and** timing cue (date, "tomorrow", "next week", etc.),  
      c) real importance (money, health/safety, hard deadline, or explicit stress if missed).  
    • Exclude vague or trivial remarks ("We should grab lunch sometime").  
    • Merge duplicates; order by due date → spoken urgency → alphabetical.  
    • Format each as a single bullet with its own emoji from the whitelist 📞 📝 🏥 🚗 💻 🛠️ 📦 📊 📚 🔧 ⚠️ ⏳ 🎯 🔋 🎓 📢 💡.

        Example format:  
        - 🗓️ **Submit Q2 budget** • due 05/31  
        - 💻 **Update project repo** • tomorrow  

    For the category, classify the conversation into one of the available categories.

    For Calendar Events, include a list of events extracted from the conversation that the user must have on their calendar. For date context, this conversation happened on {started_at}. {tz} is the user's timezone; convert all event times to UTC and respond in UTC.

    Transcript: ```{transcript}```

    {format_instructions}'''.replace('    ', '').strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_high | parser # parser is imported from .clients

    response = chain.invoke({
        'transcript': transcript.strip(),
        'title': title,
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


def get_app_result(transcript: str, app: App) -> str:
    prompt = f'''
    You are an AI with the following characteristics:
    Name: {app.name},
    Description: {app.description},
    Task: ${app.memory_prompt}

    Conversation: ```{transcript.strip()}```,
    '''

    response = llm_high.invoke(prompt)
    content = response.content.replace('```json', '').replace('```', '')
    return content


def get_app_result_v1(transcript: str, app: App) -> str:
    prompt = f'''
    You are an AI with the following characteristics:
    Name: ${app.name},
    Description: ${app.description},
    Task: ${app.memory_prompt}

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



class BestAppSelection(BaseModel):
    app_id: str = Field(
        description='The ID of the best app for processing this conversation, or an empty string if none are suitable.')


def select_best_app_for_conversation(conversation: Conversation, apps: List[App]) -> Optional[App]:
    """
    Select the best app for the given conversation based on its structured content
    and the specific task/outcome each app provides.
    """
    if not apps:
        return None

    if not conversation.structured:
        return None

    structured_data = conversation.structured
    conversation_details = f"""
    Title: {structured_data.title or 'N/A'}
    Category: {structured_data.category.value if structured_data.category else 'N/A'}
    Overview: {structured_data.overview or 'N/A'}
    Action Items: {ActionItem.actions_to_string(structured_data.action_items) if structured_data.action_items else 'None'}
    Events Mentioned: {Event.events_to_string(structured_data.events) if structured_data.events else 'None'}
    """

    apps_xml = "<apps>\n"
    for app in apps:
        apps_xml += f"""  <app>
    <id>{app.id}</id>
    <name>{app.name}</name>
    <description>{app.description}</description>
  </app>\n"""
    apps_xml += "</apps>"

    prompt = f"""
    You are an expert app selector. Your goal is to determine if any available app is genuinely suitable for processing the given conversation details based on the app's specific task and the potential value of its outcome.

    <conversation_details>
    {conversation_details.strip()}
    </conversation_details>

    <available_apps>
    {apps_xml.strip()}
    </available_apps>

    Task:
    1. Analyze the conversation's content, themes, action items, and events provided in `<conversation_details>`.
    2. For each app in `<available_apps>`, evaluate its specific `<task>` and `<description>`.
    3. Determine if applying an app's `<task>` to this specific conversation would produce a meaningful, relevant, and valuable outcome.
    4. Select the single best app whose task aligns most strongly with the conversation content and provides the most useful potential outcome.

    Critical Instructions:
    - Only select an app if its specific task is highly relevant to the conversation's topics and details. A generic match based on description alone is NOT sufficient.
    - Consider the *potential outcome* of applying the app's task. Would the result be insightful given this conversation?
    - If no app's task strongly aligns with the conversation content or offers a valuable potential outcome (e.g., a business conversation when all apps are for medical analysis), you MUST return an empty `app_id`.
    - Do not force a match. It is better to return an empty `app_id` than to select an inappropriate app.
    - Provide ONLY the `app_id` of the best matching app, or an empty string if no app is suitable.
    """

    try:
        with_parser = llm_mini.with_structured_output(BestAppSelection)
        response: BestAppSelection = with_parser.invoke(prompt)
        selected_app_id = response.app_id

        if not selected_app_id or selected_app_id.strip() == "":
            return None

        # Find the app object with the matching ID
        selected_app = next((app for app in apps if app.id == selected_app_id), None)
        if selected_app:
            return selected_app
        else:
            return None

    except Exception as e:
        print(f"Error selecting best app: {e}")
        return None


def generate_summary_with_prompt(conversation_text: str, prompt: str) -> str:
    prompt = f"""
    Your task is: {prompt}

    The conversation is:
    {conversation_text}

    You must output only the summary, no other text. Make sure to be concise and clear.
    """
    response = llm_high.invoke(prompt)
    return response.content