from fastapi import HTTPException, APIRouter

from utils.storage import upload_user_backup, retrieve_user_backup, delete_backup_storage

router = APIRouter()


@router.post('/backup')
def backup(uid: str, data: dict):
    try:
        data: str = data['data']
        if data == '':
            raise Exception
    except Exception:
        raise HTTPException(status_code=400, detail='No valid data')
    return {'url': upload_user_backup(uid, data)}


@router.get('/backup')
def get_backup(uid: str):
    return {'data': retrieve_user_backup(uid)}


@router.delete('/backup')
def delete_backup(uid: str):
    delete_backup_storage(uid)
    return 'ok'


@router.post('/v1/backups', tags=['v1'])
def backup(data: dict, uid: str):  # Depends(auth.get_current_user_uid)
    try:
        data: str = data['data']
        if data == '':
            raise Exception
    except Exception:
        raise HTTPException(status_code=400, detail='No valid data')
    return {'url': upload_user_backup(uid, data)}


@router.get('/v1/backups', tags=['v1'])
def get_backup(uid: str):  # Depends(auth.get_current_user_uid)
    return {'data': retrieve_user_backup(uid)}


@router.delete('/v1/backups', tags=['v1'])
def delete_backup(uid: str):  # = Depends(auth.get_current_user_uid)
    delete_backup_storage(uid)
    return 'ok'
