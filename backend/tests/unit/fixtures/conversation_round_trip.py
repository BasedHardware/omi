"""Producer-to-reader round trip for stored conversation rows.

A producer's output must read back through every consumer that validates it: the write seam
(``row_contract.check_write``), the reader model (``Conversation(**row)``) and the list endpoint's
declared ``response_model``, serialized to JSON as FastAPI would. Adopt it in one line::

    assert_conversation_row_round_trips(producer_output)

The endpoint model is read from the registered route, so a changed ``response_model`` is exercised
without editing the producer tests.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from fastapi.routing import APIRoute
from pydantic import BaseModel, TypeAdapter

from models.conversation import Conversation
from routers import conversations as conversations_router  # collection pays the router graph, not a test's CPU budget
from utils.conversations import row_contract

LIST_ROUTE = ('GET', '/v1/conversations')


def _response_model(method: str, path: str):
    [route] = [
        route
        for route in conversations_router.router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    ]
    return route.response_model


def stored_row(output: BaseModel | Mapping[str, Any]) -> dict:
    """The dict a producer commits: a model is stored as its ``model_dump()``."""
    return output.model_dump() if isinstance(output, BaseModel) else dict(output)


def assert_conversation_row_round_trips(output: BaseModel | Mapping[str, Any], *, route=LIST_ROUTE) -> Conversation:
    row = stored_row(output)
    row_contract.check_write(row, producer='round_trip_test')
    conversation = Conversation(**row)
    assert row_contract.readable_rows([row], surface='round_trip_test') == [row]
    adapter = TypeAdapter(_response_model(*route))
    body = json.loads(adapter.dump_json(adapter.validate_python([row])))
    assert [item['id'] for item in body] == [row['id']]
    return conversation
