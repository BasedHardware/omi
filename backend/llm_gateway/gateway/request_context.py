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


def validated_jit_budget_values(
    contract: str | None,
    run_id: str | None,
    max_attempts: str | None,
    max_output_tokens: str | None,
    max_input_tokens: str | None,
    max_spend_micro_usd: str | None,
) -> tuple[str, str, int, int, int, int] | None:
    """Validate the wire contract shared by relays and gateway requests.

    Returning normalized integers keeps the desktop relay and gateway on one
    grammar and one set of qualification ceilings.  An entirely absent
    contract is normal chat; a partially supplied contract is rejected.
    """
    values = (contract, run_id, max_attempts, max_output_tokens, max_input_tokens, max_spend_micro_usd)
    if all(value is None for value in values):
        return None
    if os.getenv(JIT_BUDGET_CONTRACT_ENV, '').strip() != JIT_CLOUD_QA_CONTRACT_VERSION:
        raise ValueError('JIT budget capability is unavailable on this gateway')
    if contract != JIT_CLOUD_QA_CONTRACT_VERSION or not run_id or not JIT_RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError('invalid JIT budget contract')
    normalized: list[int] = []
    for header, raw in zip(
        (JIT_MAX_ATTEMPTS_HEADER, JIT_MAX_OUTPUT_HEADER, JIT_MAX_INPUT_HEADER, JIT_MAX_SPEND_HEADER),
        values[2:],
        strict=True,
    ):
        try:
            value = int(raw) if raw is not None else 0
        except (TypeError, ValueError) as exc:
            raise ValueError(f'invalid JIT budget header: {header}') from exc
        if value <= 0:
            raise ValueError(f'invalid JIT budget header: {header}')
        normalized.append(value)
    ceilings = (3, 2_048, 32_768, 50_000)
    if any(value > ceiling for value, ceiling in zip(normalized, ceilings, strict=True)):
        raise ValueError('JIT budget exceeds qualification ceiling')
    return (contract, run_id, normalized[0], normalized[1], normalized[2], normalized[3])


def jit_budget_forward_headers(
    contract: str | None,
    run_id: str | None,
    max_attempts: str | None,
    max_output_tokens: str | None,
    max_input_tokens: str | None,
    max_spend_micro_usd: str | None,
) -> dict[str, str]:
    """Return canonical relay headers for a validated qualification request."""
    parsed = validated_jit_budget_values(
        contract,
        run_id,
        max_attempts,
        max_output_tokens,
        max_input_tokens,
        max_spend_micro_usd,
    )
    if parsed is None:
        return {}
    contract_value, run_value, attempts, output, input_tokens, spend = parsed
    return {
        'X-Omi-Jit-Contract-Version': contract_value,
        'X-Omi-Jit-Run-Id': run_value,
        'X-Omi-Jit-Max-Attempts': str(attempts),
        'X-Omi-Jit-Max-Output-Tokens': str(output),
        'X-Omi-Jit-Max-Input-Tokens': str(input_tokens),
        'X-Omi-Jit-Max-Spend-Micro-Usd': str(spend),
    }


def jit_budget_headers_for(request: Request, *, owner_uid: str | None = None) -> JITBudgetHeaders | None:
    """Parse the explicit qualification contract; absent means normal chat."""
    parsed = validated_jit_budget_values(
        request.headers.get(JIT_CONTRACT_HEADER),
        request.headers.get(JIT_RUN_ID_HEADER),
        request.headers.get(JIT_MAX_ATTEMPTS_HEADER),
        request.headers.get(JIT_MAX_OUTPUT_HEADER),
        request.headers.get(JIT_MAX_INPUT_HEADER),
        request.headers.get(JIT_MAX_SPEND_HEADER),
    )
    if parsed is None:
        return None
    contract, run_id, max_attempts, max_output, max_input, max_spend = parsed
    return JITBudgetHeaders(contract, run_id, max_attempts, max_output, max_input, max_spend, owner_uid)


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
