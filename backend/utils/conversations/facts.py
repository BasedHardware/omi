from typing import List, Tuple, Optional

import database.facts as facts_db
from models.facts import FactDB, Fact, CategoryEnum
from models.integrations import ExternalIntegrationCreateFact
from utils.llm import extract_facts_from_text

def process_external_integration_fact(uid: str, fact_data: ExternalIntegrationCreateFact, app_id: str) -> List[FactDB]:
    fact_data.app_id = app_id
    saved_facts = []

    # Process explicit facts if provided
    if fact_data.memories and len(fact_data.memories) > 0:
        for explicit_fact in fact_data.memories:
            # Create a Fact object from the explicit fact content
            fact = Fact(
                content=explicit_fact.content,
                category=CategoryEnum.other,
                tags=explicit_fact.tags if explicit_fact.tags else []
            )

            # Convert to FactDB
            fact_db = FactDB.from_fact(fact, uid, None, None, False)
            fact_db.manually_added = False
            fact_db.app_id = app_id
            saved_facts.append(fact_db)

    # Extract facts from text if provided
    if fact_data.text and len(fact_data.text.strip()) > 0:
        extracted_facts = extract_facts_from_text(
            uid,
            fact_data.text,
            fact_data.text_source_spec if fact_data.text_source_spec else fact_data.text_source.value
        )

        if extracted_facts and len(extracted_facts) > 0:
            # Save each extracted fact
            for fact in extracted_facts:
                fact_db = FactDB.from_fact(fact, uid, None, None, False)
                fact_db.manually_added = False
                fact_db.app_id = app_id
                saved_facts.append(fact_db)

    # Save all facts to the database if any were created
    if saved_facts:
        facts_db.save_facts(uid, [fact_db.dict() for fact_db in saved_facts])

    return saved_facts

def process_twitter_facts(uid: str, tweets_text: str, persona_id: str) -> List[FactDB]:
    # Extract facts from tweets using the LLM
    extracted_facts = extract_facts_from_text(
        uid,
        tweets_text,
        "twitter_tweets"
    )

    if not extracted_facts or len(extracted_facts) == 0:
        print(f"No facts extracted from tweets for user {uid}")
        return []

    # Convert extracted facts to database format
    saved_facts = []
    for fact in extracted_facts:
        fact_db = FactDB.from_fact(fact, uid, None, None, False)
        fact_db.manually_added = False
        fact_db.app_id = persona_id
        saved_facts.append(fact_db)

    # Save all facts in batch
    facts_db.save_facts(uid, [fact_db.dict() for fact_db in saved_facts])

    return saved_facts
