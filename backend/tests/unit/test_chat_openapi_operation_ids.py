from fastapi import FastAPI

from routers.chat import router


def test_v1_chat_operation_ids_remain_compatible_after_handler_renames():
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()['paths']

    assert paths['/v1/files']['post']['operationId'] == 'upload_file_chat_v1_files_post'
    assert (
        paths['/v1/messages/{message_id}/report']['post']['operationId']
        == 'report_message_v1_messages__message_id__report_post'
    )
    assert paths['/v1/messages']['delete']['operationId'] == 'clear_chat_messages_v1_messages_delete'
    assert paths['/v1/initial-message']['post']['operationId'] == 'create_initial_message_v1_initial_message_post'
