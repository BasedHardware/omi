from fastapi.routing import APIRoute

from routers.chat import router


def test_legacy_v1_chat_operation_ids_are_preserved_after_ruff_renames():
    operation_ids = {
        (route.path, method): route.operation_id
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    assert operation_ids[('/v1/files', 'POST')] == 'upload_file_chat_v1_files_post'
    assert (
        operation_ids[('/v1/messages/{message_id}/report', 'POST')]
        == 'report_message_v1_messages__message_id__report_post'
    )
    assert operation_ids[('/v1/messages', 'DELETE')] == 'clear_chat_messages_v1_messages_delete'
    assert operation_ids[('/v1/initial-message', 'POST')] == 'create_initial_message_v1_initial_message_post'
