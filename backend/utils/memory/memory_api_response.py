"""HTTP response builders for public memory API payloads."""

from collections.abc import Mapping
from typing import Any, Iterable

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload, memory_api_payloads


def memory_item_response(
    value: BaseModel | dict[str, Any],
    exposure: MemoryApiExposure,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(memory_api_payload(value, exposure)), headers=dict(headers or {}))


def memory_list_response(
    values: Iterable[BaseModel | dict[str, Any]],
    exposure: MemoryApiExposure,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(memory_api_payloads(values, exposure)), headers=dict(headers or {}))


def memory_batch_response(
    values: Iterable[BaseModel | dict[str, Any]],
    exposure: MemoryApiExposure,
    *,
    created_count: int,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    content = {
        'memories': memory_api_payloads(values, exposure),
        'created_count': created_count,
    }
    return JSONResponse(content=jsonable_encoder(content), headers=dict(headers or {}))
