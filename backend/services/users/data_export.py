from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence, cast

from database import chat as chat_db
from database import conversations as conversations_db
from database import memories as memories_db
from database.action_items import get_action_items as get_standalone_action_items
from database.users import get_people, get_user_profile

JsonRecord = dict[str, Any]


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _iter_paginated(
    fetch_page: Callable[[int, int], Sequence[Mapping[str, Any]]], *, batch_size: int = 1000
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = fetch_page(batch_size, offset)
        if not page:
            break
        yield from page
        if len(page) < batch_size:
            break
        offset += batch_size


def _yield_json_array(items: Iterable[Mapping[str, Any]]) -> Iterator[str]:
    yield '[\n'
    first = True
    for item in items:
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(item, default=_json_default, indent=4)
    yield '\n  ]'


def iter_user_data_export(uid: str) -> Iterator[str]:
    yield '{\n'

    profile = cast(JsonRecord | None, get_user_profile(uid))
    yield '  "profile": ' + json.dumps(profile if profile else {}, default=_json_default, indent=2) + ',\n'

    yield '  "conversations": [\n'
    first = True
    for conv in conversations_db.iter_all_conversations(uid, include_discarded=True):
        if conv is None:
            continue
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(conv, default=_json_default, indent=4)
    yield '\n  ],\n'

    yield '  "memories": '
    yield from _yield_json_array(
        _iter_paginated(
            lambda limit, offset: cast(
                Sequence[Mapping[str, Any]], memories_db.get_non_filtered_memories(uid, limit=limit, offset=offset)
            )
        )
    )
    yield ',\n'

    people = cast(Sequence[Mapping[str, Any]], get_people(uid))
    yield '  "people": ' + json.dumps(people, default=_json_default, indent=2) + ',\n'

    yield '  "action_items": '
    yield from _yield_json_array(
        _iter_paginated(
            lambda limit, offset: cast(
                Sequence[Mapping[str, Any]], get_standalone_action_items(uid, limit=limit, offset=offset)
            )
        )
    )
    yield ',\n'

    yield '  "chat_messages": [\n'
    first = True
    for msg in cast(Iterable[Mapping[str, Any]], chat_db.iter_all_messages(uid)):
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(msg, default=_json_default, indent=4)
    yield '\n  ]\n'

    yield '}\n'
