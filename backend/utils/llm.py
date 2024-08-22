import json
from datetime import datetime
from typing import List, Tuple, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

from models.chat import Message
from models.memory import Structured, MemoryPhoto, CategoryEnum
from models.plugin import Plugin
from models.transcript_segment import TranscriptSegment, ImprovedTranscript

llm = ChatOpenAI(model='gpt-4o')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
parser = PydanticOutputParser(pydantic_object=Structured)
llm_with_parser = llm.with_structured_output(Structured)


# TODO: include caching layer, redis


def improve_transcript_prompt(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    cleaned = []
    has_user = any([item.is_user for item in segments])
    for item in segments:
        speaker_id = item.speaker_id
        if has_user:
            speaker_id = item.speaker_id + 1 if not item.is_user else 0
        cleaned.append({'speaker_id': speaker_id, 'text': item.text})

    prompt = f'''
You are a helpful assistant for correcting transcriptions of recordings. You will be given a list of voice segments, each segment contains the fields (speaker id, text, and seconds [start, end])

The transcription has a Word Error Rate of about 15% in english, in other languages could be up to 25%, and it is specially bad at speaker diarization.

Your task is to improve the transcript by taking the following steps:

1. Make the conversation coherent, if someone reads it, it should be clear what the conversation is about, remember the estimate percentage of WER, this could include missing words, incorrectly transcribed words, missing connectors, punctuation signs, etc.

2. The speakers ids are most likely inaccurate, make sure to assign the correct speaker id to each segment, by understanding the whole conversation. For example, 
- The transcript could have 4 different speakers, but by analyzing the overall context, one can discover that it was only 2, and the speaker identification, took incorrectly multiple people.
- The transcript could have 1 single speaker, or 2, but in reality was 3.
- The speaker id might be assigned incorrectly, a conversation could have speaker 0 said "Hi, how are you", and then also speaker 0 said "I'm doing great, thanks for asking" which of course would be incorrect.

Considerations:
- Return a list of segments same size as the input.
- Do not change the order of the segments.

Transcript segments:
{json.dumps(cleaned, indent=2)}'''

    with_parser = llm.with_structured_output(ImprovedTranscript)
    response: ImprovedTranscript = with_parser.invoke(prompt)
    return response.result


class DiscardMemory(BaseModel):
    discard: bool = Field(description="If the memory should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


# **********************************************
# ************* MEMORY PROCESSING **************
# **********************************************

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
    chain = prompt | llm | parser
    try:
        response: DiscardMemory = chain.invoke({
            'transcript': transcript.strip(),
            'format_instructions': parser.get_format_instructions(),
        })
        return response.discard

    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return False


def get_transcript_structure(transcript: str, started_at: datetime, language_code: str) -> Structured:
    prompt = ChatPromptTemplate.from_messages([(
        'system',
        '''Your task is to provide structure and clarity to the recording transcription of a conversation.
        The conversation language is {language_code}. Use English for your response.
        
        {force_process_str}

        For the title, use the main topic of the conversation.
        For the overview, condense the conversation into a summary with the main topics discussed, make sure to capture the key points and important details from the conversation.
        For the action items, include a list of commitments, specific tasks or actionable next steps from the conversation. Specify which speaker is responsible for each action item. 
        For the category, classify the conversation into one of the available categories.
        For Calendar Events, include a list of events extracted from the conversation, that the user must have on his calendar. For date context, this conversation happened on {started_at}.
            
        Transcript: ```{transcript}```

        {format_instructions}'''.replace('    ', '').strip()
    )])
    chain = prompt | llm | parser

    response = chain.invoke({
        'transcript': transcript.strip(),
        'format_instructions': parser.get_format_instructions(),
        'language_code': language_code,
        'force_process_str': '',
        'started_at': started_at.isoformat(),
    })
    return response


def transcript_user_speech_fix(prev_transcript: str, new_transcript: str) -> int:
    prev_transcript_tokens = num_tokens_from_string(prev_transcript)
    count_user_appears = prev_transcript.count('User:')
    if count_user_appears == 0:
        return -1
    elif prev_transcript_tokens > 10000:
        # if count_user_appears == 1: # most likely matching was a mistake
        #     return -1
        first_user_appears = new_transcript.index('User:')
        # trim first user appears
        prev_transcript = prev_transcript[first_user_appears:min(first_user_appears + 10000, len(prev_transcript))]
        # new_transcript = new_transcript[first_user_appears:min(first_user_appears + 10000, len(new_transcript))]
        # further improvement

    print(f'transcript_user_speech_fix prev_transcript: {len(prev_transcript)} new_transcript: {len(new_transcript)}')
    prompt = f'''
    You will be given a previous transcript and a improved transcript, previous transcript has the user voice identified, but the improved transcript does not have it.
    Your task is to determine on the improved transcript, which speaker id corresponds to the user voice, based on the previous transcript.
    It is possible that the previous transcript has wrongly detected the user, in that case, output -1.

    Previous Transcript:
    {prev_transcript}

    Improved Transcript:
    {new_transcript}
    '''
    with_parser = llm.with_structured_output(SpeakerIdMatch)
    response: SpeakerIdMatch = with_parser.invoke(prompt)
    return response.speaker_id


def get_plugin_result(transcript: str, plugin: Plugin) -> str:
    prompt = f'''
    Your are an AI with the following characteristics:
    Name: ${plugin.name}, 
    Description: ${plugin.description},
    Task: ${plugin.memory_prompt}

    Note: It is possible that the conversation you are given, has nothing to do with your task, \
    in that case, output an empty string. (For example, you are given a business conversation, but your task is medical analysis)

    Conversation: ```{transcript.strip()}```,

    Output your response in plain text, without markdown.
    Make sure to be concise and clear.
    '''

    response = llm.invoke(prompt)
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
    return llm_with_parser.invoke(prompt)


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************

def summarize_screen_pipe(description: str) -> Structured:
    prompt = f'''The user took a series of screenshots from his laptop, and used OCR to obtain the text from the screen.

      For the title, use the main topic of the scenes.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.
    
      Screenshots: ```{description}```
      '''.replace('    ', '').strip()
    # return groq_llm_with_parser.invoke(prompt)
    return llm_with_parser.invoke(prompt)


def summarize_experience_text(text: str) -> Structured:
    prompt = f'''The user sent a text of their own experiences or thoughts, and wants to create a memory from it.

      For the title, use the main topic of the experience or thought.
      For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
      For the category, classify the scenes into one of the available categories.
    
      Text: ```{text}```
      '''.replace('    ', '').strip()
    # return groq_llm_with_parser.invoke(prompt)
    return llm_with_parser.invoke(prompt)


def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]


# ****************************************
# ************* CHAT BASICS **************
# ****************************************
def initial_chat_message(plugin: Optional[Plugin] = None) -> str:
    if plugin is None:
        prompt = '''
        You are an AI with the following characteristics:
        Name: Friend, 
        Personality/Description: A friendly and helpful AI assistant that aims to make your life easier and more enjoyable.
        Task: Provide assistance, answer questions, and engage in meaningful conversations.

        Send an initial message to start the conversation, make sure this message reflects your personality, \
        humor, and characteristics.

        Output your response in plain text, without markdown.
        '''
    else:
        prompt = f'''
        You are an AI with the following characteristics:
        Name: {plugin.name}, 
        Personality/Description: {plugin.chat_prompt},
        Task: {plugin.memory_prompt}

        Send an initial message to start the conversation, make sure this message reflects your personality, \
        humor, and characteristics.

        Output your response in plain text, without markdown.
        '''
    prompt = prompt.replace('    ', '').strip()
    return llm.invoke(prompt).content


import tiktoken

encoding = tiktoken.encoding_for_model('gpt-4')


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(encoding.encode(string))
    return num_tokens


# ***************************************************
# ************* CHAT CURRENT APP LOGIC **************
# ***************************************************


class RequiresContext(BaseModel):
    value: bool = Field(description="Based on the conversation, this tells if context is needed to respond")


class TopicsContext(BaseModel):
    topics: List[CategoryEnum] = Field(default=[], description="List of topics.")


class DatesContext(BaseModel):
    dates_range: List[datetime] = Field(default=[], description="Dates range. (Optional)")


def requires_context(messages: List[Message]) -> bool:
    prompt = f'''
    Based on the current conversation your task is to determine if the user is asking a question that requires context outside the conversation to be answered.
    Take as example: if the user is saying "Hi", "Hello", "How are you?", "Good morning", etc, the answer is False.
    
    Conversation History:    
    {Message.get_messages_as_string(messages)}
    '''
    with_parser = llm.with_structured_output(RequiresContext)
    response: RequiresContext = with_parser.invoke(prompt)
    return response.value


# TODO: try query expansion, instead of topics / queries
# TODO: include user name in prompt, and preferences.

def retrieve_context_params(messages: List[Message]) -> List[str]:
    prompt = f'''
    Based on the current conversation an AI and a User are having, for the AI to answer the latest user messages, it needs context outside the conversation.
    
    Your task is to extract the correct and most accurate context in the conversation, to be used to retrieve more information.
    Provide a list of topics in which the current conversation needs context about, in order to answer the most recent user request.
    
    It is possible that the data needed is not related to a topic, in that case, output an empty list. 

    Conversation:
    {Message.get_messages_as_string(messages)}
    '''.replace('    ', '').strip()
    with_parser = llm.with_structured_output(TopicsContext)
    response: TopicsContext = with_parser.invoke(prompt)
    topics = list(map(lambda x: str(x.value).capitalize(), response.topics))
    return topics


def retrieve_context_dates(messages: List[Message]) -> List[datetime]:
    prompt = f'''
    Based on the current conversation an AI and a User are having, for the AI to answer the latest user messages, it needs context outside the conversation.
    
    Your task is to to find the dates range in which the current conversation needs context about, in order to answer the most recent user request.
    
    For example, if the user request relates to "What did I do last week?", or "What did I learn yesterday", or "Who did I meet today?", the dates range should be provided. 
    Other type of dates, like historical events, or future events, should be ignored and an empty list should be returned.
    

    Conversation:
    {Message.get_messages_as_string(messages)}
    '''.replace('    ', '').strip()
    with_parser = llm.with_structured_output(DatesContext)
    response: DatesContext = with_parser.invoke(prompt)
    return response.dates_range


def determine_requires_context(messages: List[Message]) -> Optional[Tuple[List[str], List[datetime]]]:
    prompt = '''
            Based on the current conversation an AI and a User are having, determine if the AI requires context outside the conversation to respond to the user's message.
            More context could mean, user stored old conversations, notes, or information that seems very user-specific.
    
            - First determine if the conversation requires context, in the field "requires_context".
            - Context could be 2 different things:
              - A list of topics (each topic being 1 or 2 words, e.g. "Startups" "Funding" "Business Meeting" "Artificial Intelligence") that are going to be used to retrieve more context, in the field "topics". Leave an empty list if not context is needed.
              - A dates range, if the context is time-based, in the field "dates_range". Leave an empty list if not context is needed. FYI if the user says today, today is {current_date}.
    
            Conversation:
            {conversation}
            
            {format_instructions}
        '''.replace('    ', '').strip()
    parser = PydanticOutputParser(pydantic_object=TopicsContext)

    prompt = PromptTemplate(
        template=prompt,
        input_variables=["current_date", "conversation"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    conversation = Message.get_messages_as_string(messages)

    prompt_and_model = prompt | llm
    output = prompt_and_model.invoke({'current_date': datetime.now().isoformat(), 'conversation': conversation})

    try:
        parsed_output = parser.invoke(output)
        topics = parsed_output.topics
        dates = parsed_output.dates_range
        print(f'topics: {topics}, dates: {dates}')
        return (topics, dates) if parsed_output.requires_context else None
    except Exception as e:
        print(f'Error determining requires context: {e}')
        return None


class SummaryOutput(BaseModel):
    summary: str = Field(description="The extracted summary from the conversation, at most 250 tokens.")


def chunk_extraction(segments: List[TranscriptSegment], topics: List[str]) -> str:
    content = TranscriptSegment.segments_as_string(segments)
    prompt = f'''
    You will be given a conversation transcript, and a list of topics.
    Your task is to generate a summary of the conversation focused on the topics provided.
    Include the most relevant information about the topics, people mentioned, events, locations, facts, phrases, and any other relevant information.
    It is possible the topics are not related to the conversation, in that case, output an empty string.
    
    Conversation:
    {content}
    
    Topics: {topics}
    
    '''
    with_parser = llm.with_structured_output(SummaryOutput)
    response: SummaryOutput = with_parser.invoke(prompt)
    return response.summary


def qa_rag(context: str, messages: List[Message], plugin: Optional[Plugin] = None) -> str:
    conversation_history = Message.get_messages_as_string(
        messages, use_user_name_if_available=True, use_plugin_name_if_available=True
    )

    plugin_info = ""
    if plugin:
        plugin_info = f"Your name is: {plugin.name}, and your personality/description is '{plugin.description}'.\nMake sure to reflect your personality in your response.\n"

    prompt = f"""
    You are an assistant for question-answering tasks. Use the following pieces of retrieved context and the conversation history to continue the conversation.
    If you don't know the answer, just say that you didn't find any related information or you that don't know. Use three sentences maximum and keep the answer concise.
    If the message doesn't require context, it will be empty, so follow-up the conversation casually.
    If there's not enough information to provide a valuable answer, ask the user for clarification questions.
    {plugin_info}
    
    Conversation History:
    {conversation_history}

    Context:
    ```
    {context}
    ```
    Answer:
    """.replace('    ', '').strip()
    print(prompt)
    return llm.invoke(prompt).content
