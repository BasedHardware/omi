import json
import os
from datetime import datetime, timezone, date
from typing import List

import firebase_admin
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

llm_mini = ChatOpenAI(model='gpt-4o-mini')
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
firebase_admin.initialize_app()

from database._client import get_users_uid
import database.memories as memories_db


class ExtractedInformation(BaseModel):
    people_mentioned: List[str] = Field(
        default=[],
        description='Identify all the people names who were mentioned during the conversation.'
    )
    topics_discussed: List[str] = Field(
        default=[],
        description='List all the main topics and subtopics that were discussed.',
    )
    # recommendations: List[dict] = Field(
    #     default=[],
    #     description='Extract any recommendations made, specifying who made them and what they are about.'
    # )
    entities: List[str] = Field(
        default=[],
        description='List any products, technologies, places, or other entities that are relevant to the conversation.'
    )
    dates: List[date] = Field(
        default=[],
        description=f'Extract any dates mentioned in the conversation. Use the format YYYY-MM-DD.'
    )


def generate(created_at: str, transcript_segment: List[dict]) -> ExtractedInformation:
    transcript = ''
    for segment in transcript_segment:
        transcript += f'{segment["text"].strip()}\n\n'

    # TODO: tell it to prioritize existing options for each field, or how to standardize search?

    prompt = f'''
    You will be given the raw transcript of a conversation, this transcript has about 20% word error rate, 
    and diarization is also made very poorly.
    
    Your task is to extract the most accurate information from the conversation in the output object indicated below.
    
    Make sure as a first step, you infer and fix the raw transcript errors and then proceed to extract the information.
    
    For context when extracting dates, today is {created_at}.
    If one says "today", it means the current day.
    If one says "tomorrow", it means the next day after today.
    If one says "yesterday", it means the day before today.
    If one says "next week", it means the next monday.
    
    Conversation Transcript:
    ```
    {transcript}
    ```
    '''.replace('    ', '')
    result: ExtractedInformation = llm_mini.with_structured_output(ExtractedInformation).invoke(prompt)
    print(json.dumps(result.dict(), indent=2, default=str))
    return result


if __name__ == '__main__':
    uids = get_users_uid()
    for uid in ['TtCJi59JTVXHmyUC6vUQ1d9U6cK2']:
        memories = memories_db.get_memories(uid, limit=50)
        to_merge = []
        for memory in memories:
            created_at = datetime.fromtimestamp(memory['created_at'].timestamp(), tz=timezone.utc)
            generate(created_at.strftime('%Y-%m-%d'), memory['transcript_segments'])
