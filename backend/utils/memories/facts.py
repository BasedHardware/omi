from typing import List, Tuple, Optional

import database.facts as facts_db
from database.auth import get_user_name
from models.facts import Fact, FactDB
from models.integrations import ExternalIntegrationCreateFact


def get_prompt_facts(uid: str) -> str:
    user_name, user_made_facts, generated_facts = get_prompt_data(uid)
    facts_str = f'you already know the following facts about {user_name}: \n{Fact.get_facts_as_str(generated_facts)}.'
    if user_made_facts:
        facts_str += f'\n\n{user_name} also shared the following about self: \n{Fact.get_facts_as_str(user_made_facts)}'
    return user_name, facts_str + '\n'


def get_prompt_data(uid: str) -> Tuple[str, List[Fact], List[Fact]]:
    # TODO: cache this
    existing_facts = facts_db.get_facts(uid, limit=100)
    user_made = [Fact(**fact) for fact in existing_facts if fact['manually_added']]
    # TODO: filter only reviewed True
    generated = [Fact(**fact) for fact in existing_facts if not fact['manually_added']]
    user_name = get_user_name(uid)
    # print('get_prompt_data', user_name, len(user_made), len(generated))
    return user_name, user_made, generated


def extract_facts_from_text(
        uid: str, text: str, text_source: str, user_name: Optional[str] = None, facts_str: Optional[str] = None
) -> List[Fact]:
    """Extract facts from external integration text sources like email, posts, messages"""
    if user_name is None or facts_str is None:
        user_name, facts_str = get_prompt_facts(uid)

    if not text or len(text) < 25:  # less than 5 words, probably nothing
        return []

    try:
        from utils.llm import PydanticOutputParser, Facts, extract_facts_text_content_prompt, llm_mini
        parser = PydanticOutputParser(pydantic_object=Facts)
        chain = extract_facts_text_content_prompt | llm_mini | parser
        response: Facts = chain.invoke({
            'user_name': user_name,
            'text_content': text,
            'text_source': text_source,
            'facts_str': facts_str,
            'format_instructions': parser.get_format_instructions(),
        })
        return response.facts
    except Exception as e:
        print(f'Error extracting facts from {text_source}: {e}')
        return []


def process_external_integration_fact(uid: str, fact_data: ExternalIntegrationCreateFact, app_id: str) -> List[FactDB]:
    """
    Process and save facts from external integration.

    Args:
        uid: User ID
        fact_data: The fact data from external integration
        app_id: The app ID that created the fact

    Returns:
        List of saved FactDB objects
    """
    # Set app_id
    fact_data.app_id = app_id

    # Extract facts from text
    extracted_facts = extract_facts_from_text(
        uid,
        fact_data.text,
        fact_data.text_source_spec if fact_data.text_source_spec else fact_data.text_source.value
    )
    if not extracted_facts or len(extracted_facts) == 0:
        return []

    saved_facts = []

    # Save each extracted fact
    for fact in extracted_facts:
        fact_db = FactDB.from_fact(fact, uid, None, None)
        fact_db.manually_added = False
        fact_db.app_id = app_id
        saved_facts.append(fact_db)
    facts_db.save_facts(uid, [fact_db.dict() for fact_db in saved_facts])

    return saved_facts
