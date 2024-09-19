from typing import List

from fastapi import APIRouter, Depends

import database.facts as facts_db
from models.facts import FactDB, Fact
from utils.other import endpoints as auth

router = APIRouter()


@router.post('/v1/facts', tags=['facts'], response_model=FactDB)
def create_fact(fact: Fact, uid: str = Depends(auth.get_current_user_uid)):
    fact_db = FactDB.from_fact(fact, uid, None, None)
    fact_db.manually_added = True
    facts_db.create_fact(uid, fact_db.dict())
    return fact_db


@router.get('/v1/facts', tags=['facts'], response_model=List[FactDB])  # filters
def get_facts(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    facts = facts_db.get_facts(uid, limit, offset)
    # TODO: consider this "$name" part if really is an issue, when changing name or smth.
    # TODO: what happens when "The User" is at the beggining, user will feel it random.
    # TODO: consider replika facts categories, probably perform better.
    # Family & Friends, Temporary, Background, Favorites, Appearance, Hopes & Goals, Opinions, Personality, Other
    # TODO: consider and automatic weekly revision (cronjob) for the user facts, to maybe simplify them, condense them.
    # for example, if the user opened the page, and went through a few, and didn't remove them, they are probably good.
    # but the ones that don't were opened or seen, can be condensed, or removed. Also with more context over time.
    # TODO: chat will need tool functions to get name, get user facts, filtered, add, or remove based on conversations.

    # user_name = get_user_name(uid, use_default=False)
    # for fact in facts:
    #     if fact['manually_added']:
    #         continue
    #     if user_name:
    #         fact['content'] = f'{user_name} {fact["content"]}'
    #     else:
    #         fact['content'] = str(fact["content"]).capitalize()
    return facts


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
    # first_word = value.split(' ')[0]
    # user_name = get_user_name(uid, use_default=False)
    # if user_name == first_word:
    #     value = value[len(first_word):].strip()

    facts_db.edit_fact(uid, fact_id, value)
    return {'status': 'ok'}
