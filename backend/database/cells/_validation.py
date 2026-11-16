"""Validation shared by every space-scoped entry point."""

import re

_ID = re.compile(r'^[A-Za-z0-9_.:@-]{1,128}$')
_ENTITY = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


def validate_id(value: object) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('invalid space or user id')


def validate_address(entity: object, entity_id: object) -> None:
    if not isinstance(entity, str) or not _ENTITY.fullmatch(entity):
        raise ValueError('invalid entity')
    if not isinstance(entity_id, str) or not 1 <= len(entity_id) <= 256 or '\x00' in entity_id:
        raise ValueError('invalid entity id')


def validate_document(value: object) -> None:
    if not isinstance(value, dict):
        raise TypeError('cell document must be a dict')
