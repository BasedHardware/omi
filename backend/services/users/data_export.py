from __future__ import annotations

import json
from datetime import datetime
from typing import Iterator

from database import chat as chat_db
from database import conversations as conversations_db
from database import memories as memories_db
from database.action_items import get_action_items as get_standalone_action_items
from database.users import get_people, get_user_profile


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def iter_user_data_export(uid: str) -> Iterator[str]:
    profile = get_user_profile(uid)
    memories_list = memories_db.get_memories(uid, limit=10000, offset=0)
    people = get_people(uid)
    action_items = get_standalone_action_items(uid, limit=10000, offset=0)

    yield '{\n'
    yield '  "profile": ' + json.dumps(profile if profile else {}, default=_json_default, indent=2) + ',\n'

    yield '  "conversations": [\n'
    first = True
    for conv in conversations_db.iter_all_conversations(uid, include_discarded=True):
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(conv, default=_json_default, indent=4)
    yield '\n  ],\n'

    yield '  "memories": ' + json.dumps(memories_list, default=_json_default, indent=2) + ',\n'
    yield '  "people": ' + json.dumps(people, default=_json_default, indent=2) + ',\n'
    yield '  "action_items": ' + json.dumps(action_items, default=_json_default, indent=2) + ',\n'

    yield '  "chat_messages": [\n'
    first = True
    for msg in chat_db.iter_all_messages(uid):
        if not first:
            yield ',\n'
        first = False
        yield '    ' + json.dumps(msg, default=_json_default, indent=4)
    yield '\n  ]\n'

    yield '}\n'
