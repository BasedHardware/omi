from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

from fastapi import Request

REQUEST_ID_HEADER = 'x-omi-request-id'
REQUEST_ID_MAX_LENGTH = 64
JIT_CONTRACT_HEADER = 'x-omi-jit-contract-version'
JIT_RUN_ID_HEADER = 'x-omi-jit-run-id'
JIT_MAX_ATTEMPTS_HEADER = 'x-omi-jit-max-attempts'
JIT_MAX_OUTPUT_HEADER = 'x-omi-jit-max-output-tokens'
JIT_MAX_INPUT_HEADER = 'x-omi-jit-max-input-tokens'
JIT_MAX_SPEND_HEADER = 'x-omi-jit-max-spend-micro-usd'
JIT_CLOUD_QA_CONTRACT_VERSION = 'jit-cloud-qa-v1'
JIT_BUDGET_CONTRACT_ENV = 'OMI_JIT_PROACTIVITY_BUDGET_CONTRACT'
JIT_RUN_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$')


@dataclass(frozen=True)
class JITBudgetHeaders:
    contract_version: str
    run_id: str
    max_attempts: int
    max_output_tokens: int
    max_input_tokens: int
    max_spend_micro_usd: int
    owner_uid: str | None = None


def jit_budget_headers_for(request: Request, *, owner_uid: str | None = None) -> JITBudgetHeaders | None:
    """Parse the explicit qualification contract; absent means normal chat."""
    contract = request.headers.get(JIT_CONTRACT_HEADER)
    if contract is None:
        return None
    if contract != JIT_CLOUD_QA_CONTRACT_VERSION:
        raise ValueError('unsupported JIT budget contract')
    if os.getenv(JIT_BUDGET_CONTRACT_ENV, '').strip() != JIT_CLOUD_QA_CONTRACT_VERSION:
        raise ValueError('JIT budget capability is unavailable on this gateway')
    run_id = request.headers.get(JIT_RUN_ID_HEADER, '')
    if not JIT_RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError('invalid JIT run ID')
    values: list[int] = []
    for header in (
        JIT_MAX_ATTEMPTS_HEADER,
        JIT_MAX_OUTPUT_HEADER,
        JIT_MAX_INPUT_HEADER,
        JIT_MAX_SPEND_HEADER,
    ):
        raw = request.headers.get(header)
        try:
            value = int(raw) if raw is not None else 0
        except ValueError as exc:
            raise ValueError(f'invalid JIT budget header: {header}') from exc
        if value <= 0:
            raise ValueError(f'invalid JIT budget header: {header}')
        values.append(value)
    # The client may request tighter bounds, never looser ones.
    if values[0] > 3 or values[1] > 2_048 or values[2] > 32_768 or values[3] > 50_000:
        raise ValueError('JIT budget exceeds qualification ceiling')
    return JITBudgetHeaders(contract, run_id, values[0], values[1], values[2], values[3], owner_uid)


def request_id_for(request: Request) -> str:
    request_id = getattr(request.state, 'request_id', None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return 'unknown'


def resolve_request_id(raw_request_id: str | None) -> str:
    """Accept only canonical UUID request IDs; generate an opaque ID otherwise."""
    if raw_request_id is not None:
        candidate = raw_request_id.strip()[:REQUEST_ID_MAX_LENGTH]
        try:
            parsed = uuid.UUID(candidate)
        except (ValueError, AttributeError):
            pass
        else:
            if str(parsed) == candidate.lower():
                return str(parsed)
    return str(uuid.uuid4())
