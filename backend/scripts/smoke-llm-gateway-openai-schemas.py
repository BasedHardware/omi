#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.gateway.schemas import ProviderRef
from models.structured_extraction import ActionItemsExtraction, ConversationStructureExtraction
from utils.llm.chat import RequiresContext
from utils.llm.gateway_client import _chat_structured_payload

PROVIDER_REF = ProviderRef(provider='openai', model='gpt-4.1-mini')
SMOKE_FEATURES = (
    ('chat_extraction.requires_context', RequiresContext),
    ('conversation_structure.extract.shadow', ConversationStructureExtraction),
    ('conversation_action_items.extract.shadow', ActionItemsExtraction),
)


async def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Smoke-test live OpenAI acceptance of LLM gateway structured-output schemas.'
    )
    parser.add_argument(
        '--timeout-ms',
        type=int,
        default=8000,
        help='Per-request timeout in milliseconds. Defaults to 8000.',
    )
    args = parser.parse_args(argv)

    if not os.getenv('OPENAI_API_KEY'):
        parser.error('OPENAI_API_KEY is required')

    provider = OpenAICompatibleChatCompletionProvider()
    try:
        for feature, output_model in SMOKE_FEATURES:
            request = _chat_structured_payload(
                'Return the smallest valid JSON object for this schema. Do not include prose.',
                output_model,
                feature=feature,
            )
            request['model'] = PROVIDER_REF.model
            request['max_completion_tokens'] = 128
            request.pop('metadata', None)
            response = await provider.create_chat_completion(
                request,
                provider_ref=PROVIDER_REF,
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=args.timeout_ms,
            )
            content = response['choices'][0]['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError(f'{feature}: provider returned empty content')
            print(f'{feature}: ok')
    finally:
        await provider.aclose()
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
