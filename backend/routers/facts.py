from fastapi import APIRouter, Depends

import database.facts as facts_db
from utils.other import endpoints as auth

router = APIRouter()


@router.get('/v1/facts', tags=['facts'])  # filters
def get_facts(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    return facts_db.get_facts(uid, limit, offset)


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
