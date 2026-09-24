import re

with open('backend/routers/apps.py', 'r') as f:
    content = f.read()

# Add AppRejectRequest
new_class = """
class AppRejectRequest(PydanticBaseModel):
    reason: str

class AppMigrationResponse"""
content = content.replace("class AppMigrationResponse", new_class)

# Update reject_app
old_func = """@router.post('/v1/apps/{app_id}/reject', tags=['v1'], response_model=AppMutationResponse)
def reject_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, False)
    invalidate_approved_apps_cache()  # App removed from public list, invalidate cache
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)
    # TODO: Add reason for rejection in payload and also redirect to the app page
    send_notification(
        uid,
        'App Rejected 😔',
        f'Your app {app["name"]} has been rejected. Please make the necessary changes and resubmit for approval.',
    )
    return {'status': 'ok'}"""

new_func = """@router.post('/v1/apps/{app_id}/reject', tags=['v1'], response_model=AppMutationResponse)
def reject_app(app_id: str, uid: str, data: AppRejectRequest = Body(...), secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, False)
    invalidate_approved_apps_cache()  # App removed from public list, invalidate cache
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)

    send_notification(
        uid,
        'App Rejected 😔',
        f'Your app {app["name"]} has been rejected. Reason: {data.reason}. Please make the necessary changes and resubmit for approval.',
        {'app_id': app_id, 'type': 'app_rejected', 'navigate_to': f'/apps/{app_id}'}
    )
    return {'status': 'ok'}"""
content = content.replace(old_func, new_func)

with open('backend/routers/apps.py', 'w') as f:
    f.write(content)
