import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import database.facts as facts_db
from models.facts import FactDB, Fact, FactCategory
from utils.apps import update_personas_async
from utils.llm import identify_category_for_fact
from utils.other import endpoints as auth

router = APIRouter()


@router.post('/v1/facts', tags=['facts'], response_model=FactDB)
def create_fact(fact: Fact, uid: str = Depends(auth.get_current_user_uid)):
    fact_db = FactDB.from_fact(fact, uid, None, None, True)
    facts_db.create_fact(uid, fact_db.dict())
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return fact_db


@router.post('/v2/facts', tags=['facts'], response_model=FactDB)
def create_fact(fact: Fact, uid: str = Depends(auth.get_current_user_uid)):
    categories = [category for category in FactCategory]
    fact.category = identify_category_for_fact(fact.content, categories)
    fact_db = FactDB.from_fact(fact, uid, None, None, True)
    facts_db.create_fact(uid, fact_db.dict())
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return fact_db


@router.get('/v1/facts', tags=['facts'], response_model=List[FactDB])  # filters
def get_facts_v1(limit: int = 5000, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    facts = facts_db.get_facts(uid, limit, offset)
    # facts = list(filter(lambda x: x['category'] == 'skills', facts))
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
    # print(len(facts))
    # return list(sorted(facts, key=lambda x: x['category'], reverse=True))
    # print(list(map(lambda x: x['category'], facts)))
    return list(filter(lambda x: x['category'] != 'learnings' and x['category'] != 'core', facts))
    # return facts


@router.get('/v2/facts', tags=['facts'], response_model=List[FactDB])
def get_facts(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    # Use high limits for the first page
    # Warn: should remove
    if offset == 0:
        limit = 5000
    facts = facts_db.get_facts(uid, limit, offset)
    return facts


@router.delete('/v1/facts/{fact_id}', tags=['facts'])
def delete_fact(fact_id: str, uid: str = Depends(auth.get_current_user_uid)):
    facts_db.delete_fact(uid, fact_id)
    return {'status': 'ok'}


@router.delete('/v1/facts', tags=['facts'])
def delete_fact(uid: str = Depends(auth.get_current_user_uid)):
    facts_db.delete_all_facts(uid)
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


@router.patch('/v1/facts/{fact_id}/visibility', tags=['facts'])
def update_fact_visibility(fact_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    if value not in ['public', 'private']:
        raise HTTPException(status_code=400, detail='Invalid visibility value')
    facts_db.change_fact_visibility(uid, fact_id, value)
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return {'status': 'ok'}
