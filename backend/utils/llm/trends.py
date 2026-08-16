from typing import Any, List, Optional, cast
from pydantic import BaseModel, Field

import database.users as users_db
from database.auth import get_user_name
from models.other import Person
from models.transcript_segment import TranscriptSegment
from models.trend import (
    TrendEnum,
    ceo_options,
    company_options,
    software_product_options,
    hardware_product_options,
    ai_product_options,
    TrendType,
)
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
import logging

logger = logging.getLogger(__name__)

PersonRecord = dict[str, Any]


class Item(BaseModel):
    category: TrendEnum = Field(description="The category identified")
    type: TrendType = Field(description="The sentiment identified")
    topic: str = Field(description="The specific topic corresponding the category")


class ExpectedOutput(BaseModel):
    items: List[Item] = Field(default=[], description="List of items.")


def trends_extractor(uid: str, transcript_segments: List[TranscriptSegment], person_ids: List[str]) -> List[Item]:
    people: list[Person] = []
    if person_ids:
        people_data: list[PersonRecord] = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    raw_user_name = cast(object, get_user_name(uid, use_default=False))
    user_name: Optional[str] = raw_user_name if isinstance(raw_user_name, str) else None
    transcript = TranscriptSegment.segments_as_string(
        transcript_segments, include_timestamps=False, user_name=user_name, people=people
    )
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
        with track_usage(uid, Features.TRENDS):
            with_parser = get_llm('trends').with_structured_output(ExpectedOutput)
            response = cast(ExpectedOutput, with_parser.invoke(prompt))
        filtered: list[Item] = []
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
        logger.error(f'Error determining memory discard: {e}')
        return []
