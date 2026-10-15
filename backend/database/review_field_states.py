"""Pure field presence and deletion states shared by reversible writers."""

import copy
from google.cloud import firestore


def read_field_state(data: dict, path: str) -> dict:
    value = data
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return {'present': False}
        value = value[key]
    return {'present': True, 'value': copy.deepcopy(value)}


def write_field_state(value: dict):
    return value['value'] if value['present'] else firestore.DELETE_FIELD
