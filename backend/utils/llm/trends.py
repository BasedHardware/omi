from typing import List
from pydantic import BaseModel, Field

import database.users as users_db
from models.conversation import Conversation
from models.other import Person
from models.trend import (
    TrendEnum,
    ceo_options,
    company_options,
    software_product_options,
    hardware_product_options,
    ai_product_options,
    TrendType,
)
from utils.llm.clients import llm_mini


class Item(BaseModel):
    category: TrendEnum = Field(description="The category identified")
    type: TrendType = Field(description="The sentiment identified")
    topic: str = Field(description="The specific topic corresponding the category")


class ExpectedOutput(BaseModel):
    items: List[Item] = Field(default=[], description="List of items.")


def trends_extractor(uid: str, memory: Conversation) -> List[Item]:
    person_ids = [s.person_id for s in memory.transcript_segments if s.person_id]
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    transcript = memory.get_transcript(False, people=people)
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
    '''.replace(
        '    ', ''
    ).strip()
    try:
        with_parser = llm_mini.with_structured_output(ExpectedOutput)
        response: ExpectedOutput = with_parser.invoke(prompt)
        filtered = []
        for item in response.items:
            if item.topic not in [
                e
                for e in (
                    ceo_options
                    + company_options
                    + software_product_options
                    + hardware_product_options
                    + ai_product_options
                )
            ]:
                continue
            filtered.append(item)
        return filtered

    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return []
