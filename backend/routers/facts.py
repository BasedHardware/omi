from typing import List

from fastapi import APIRouter, Depends

import database.facts as facts_db
from models.facts import FactDB, Fact
from utils.other import endpoints as auth

router = APIRouter()


@router.post('/v1/facts', tags=['facts'], response_model=FactDB)
def create_fact(fact: Fact, uid: str = Depends(auth.get_current_user_uid)):
    fact_db = FactDB.from_fact(fact, uid, None, None)
    facts_db.create_fact(uid, fact_db.dict())
    return fact_db


@router.get('/v1/facts', tags=['facts'], response_model=List[FactDB])  # filters
def get_facts(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    facts = facts_db.get_facts(uid, limit, offset)
    filtered = []
    for fact in facts:
        if fact['reviewed'] and not fact['user_review']:
            # skip facts that were reviewed and the user marked as false
            continue
        filtered.append(fact)
    return filtered


@router.delete('/v1/facts/{fact_id}', tags=['facts'])
def delete_fact(fact_id: str, uid: str = Depends(auth.get_current_user_uid)):
    facts_db.delete_fact(uid, fact_id)
    return {'status': 'ok'}


@router.post('/v1/facts/{fact_id}/review', tags=['facts'])
def review_fact(fact_id: str, value: bool, uid: str = Depends(auth.get_current_user_uid)):
    facts_db.review_fact(uid, fact_id, value)
    return {'status': 'ok'}


@router.patch('/v1/facts/{fact_id}', tags=['facts'])
def edit_fact(fact_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    facts_db.edit_fact(uid, fact_id, value)
    return {'status': 'ok'}
