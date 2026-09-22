"""People tool descriptors and execution for the hosted MCP server."""

from typing import Any

from utils.mcp_data import clean_person
from database.person_aliases import normalized_person_alias

MCP_PEOPLE_TOOL_NAMES = frozenset({'get_people', 'rename_person', 'dismiss_person'})
PEOPLE_READ_SECURITY = [{'type': 'oauth2', 'scopes': ['people.read']}]
PEOPLE_RENAME_SECURITY = [{'type': 'oauth2', 'scopes': ['people.rename']}]
PEOPLE_CLEANUP_SECURITY = [{'type': 'oauth2', 'scopes': ['people.cleanup']}]


def build_people_tools(
    read_annotations: dict[str, bool],
    write_annotations: dict[str, bool],
    destructive_write_annotations: dict[str, bool],
) -> list[dict[str, Any]]:
    """Build People descriptors without coupling this module to the MCP router."""

    return [
        {
            'name': 'get_people',
            'description': (
                "Retrieve the people/contacts the user interacts with (recurring speakers Omi has identified). "
                "Returns each person's name, id, and a few transcript samples of how they speak. Use this to reason "
                "about the user's relationships, not just raw text."
            ),
            'annotations': read_annotations,
            'securitySchemes': PEOPLE_READ_SECURITY,
            'inputSchema': {'type': 'object', 'properties': {}},
        },
        {
            'name': 'rename_person',
            'description': (
                "Correct a recognized person's display name. The previous name is retained as an alias, and the "
                'response contains only the person id and corrected name.'
            ),
            'annotations': write_annotations,
            'securitySchemes': PEOPLE_RENAME_SECURITY,
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'person_id': {'type': 'string', 'description': 'The person ID returned by get_people'},
                    'name': {
                        'type': 'string',
                        'description': 'Corrected display name',
                        'minLength': 1,
                        'maxLength': 128,
                    },
                },
                'required': ['person_id', 'name'],
            },
        },
        {
            'name': 'dismiss_person',
            'description': (
                'Soft-dismiss a false-positive person. The record and its history are preserved for export, but it is '
                'excluded from normal People reads. This does not hard-delete speech samples or history.'
            ),
            'annotations': destructive_write_annotations,
            'securitySchemes': PEOPLE_CLEANUP_SECURITY,
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'person_id': {'type': 'string', 'description': 'The false-positive person ID'},
                },
                'required': ['person_id'],
            },
        },
    ]


def execute_people_tool(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: str,
    error_type: Any,
    users_db: Any,
) -> dict[str, Any]:
    """Execute a People MCP tool, raising the router's protocol error type."""

    if tool_name == 'get_people':
        return {'people': [clean_person(person) for person in users_db.get_people(user_id)]}

    person_id = arguments.get('person_id')
    if not isinstance(person_id, str) or not person_id.strip():
        raise error_type('person_id is required', code=-32602)
    person_id = person_id.strip()

    if tool_name == 'rename_person':
        name = arguments.get('name')
        if not isinstance(name, str):
            raise error_type('name is required', code=-32602)
        normalized_name = normalized_person_alias(name)
        if normalized_name is None:
            raise error_type('name must contain 1 to 128 characters', code=-32602)
        if not users_db.update_person(user_id, person_id, normalized_name):
            raise error_type('Person not found', code=-32001)
        return {'success': True, 'person': {'id': person_id, 'name': normalized_name}}

    if tool_name == 'dismiss_person':
        if not users_db.dismiss_person(user_id, person_id):
            raise error_type('Person not found', code=-32001)
        return {'success': True, 'person_id': person_id, 'dismissed': True}

    raise ValueError(f'Unsupported People tool: {tool_name}')
