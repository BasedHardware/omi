"""Golden request fingerprints captured from main before the extraction."""

import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.idempotency_store import ACTIVE_SECRET_ENV, SECONDARY_SECRET_ENV, Operation, _KeyRing
from llm_gateway.idempotency_request import CredentialSource, canonical_request, parse_forwarded_byok_headers

# Captured from 439cec089818940138879bd99a15dec2d502b5d8 using its
# Operation.canonical_request and _KeyRing.fingerprint with synthetic inputs.
_GOLDEN = {
    'managed': (
        (
            b'[{"messages":[{"content":"Synthetic notes.","role":"user"}],"model":"omi:auto:conv-structure","'
            b'response_format":{"json_schema":{"name":"notes","schema":{"properties":{"summary":{"type":"stri'
            b'ng"},"title":{"type":"string"}},"type":"object"}},"type":"json_schema"}},"omi_managed",{},[[["r'
            b'esponse_format","json_schema","schema"],["title","summary"]]]]'
        ),
        'a97564e2f4fdc9a068aaf81cbf37060a6c7fec4e30ba08385c14ad9634f48619',
    ),
    'byok': (
        (
            b'[{"messages":[{"content":"Synthetic notes.","role":"user"}],"model":"omi:auto:conv-structure","'
            b'response_format":{"json_schema":{"name":"notes","schema":{"properties":{"summary":{"type":"stri'
            b'ng"},"title":{"type":"string"}},"type":"object"}},"type":"json_schema"}},"service_forwarded_byo'
            b'k",{"openai":"synthetic-openai"},[[["response_format","json_schema","schema"],["title","summary'
            b'"]]]]'
        ),
        'a00b1e859fbcf8ac0c7d09b64e698ae56719dc19440421a1acf41abf174552f4',
    ),
    'forwarded-keys': (
        (
            b'[{"messages":[{"content":"Synthetic notes.","role":"user"}],"model":"omi:auto:conv-structure","'
            b'response_format":{"json_schema":{"name":"notes","schema":{"properties":{"summary":{"type":"stri'
            b'ng"},"title":{"type":"string"}},"type":"object"}},"type":"json_schema"}},"service_forwarded_byo'
            b'k",{"anthropic":"synthetic-anthropic","openai":"synthetic-rotated"},[[["response_format","json_'
            b'schema","schema"],["title","summary"]]]]'
        ),
        '1c21f5b35a80ef0ec7995ff10079422bbd35547b33809e70e3e1ea8793478ed8',
    ),
    'reordered-schema': (
        (
            b'[{"messages":[{"content":"Synthetic notes.","role":"user"}],"model":"omi:auto:conv-structure","'
            b'response_format":{"json_schema":{"name":"notes","schema":{"properties":{"summary":{"type":"stri'
            b'ng"},"title":{"type":"string"}},"type":"object"}},"type":"json_schema"}},"omi_managed",{},[[["r'
            b'esponse_format","json_schema","schema"],["summary","title"]]]]'
        ),
        'bc619db8bdcf6b766a1d542aefbe7a05d809c40ee024b3dbfc9a06df29359000',
    ),
}


@pytest.mark.parametrize(
    'name,property_names,headers',
    [
        ('managed', ('title', 'summary'), {}),
        ('byok', ('title', 'summary'), {'X-Omi-Byok-OpenAI-Key': ' synthetic-openai '}),
        (
            'forwarded-keys',
            ('title', 'summary'),
            {
                'X-Omi-Byok-OpenAI-Key': ' synthetic-rotated ',
                'X-Omi-Byok-Anthropic-Key': 'synthetic-anthropic',
            },
        ),
        ('reordered-schema', ('summary', 'title'), {}),
    ],
)
def test_extracted_request_matches_main_golden_bytes_and_fingerprint(name, property_names, headers, monkeypatch):
    body = {
        'model': 'omi:auto:conv-structure',
        'messages': [{'role': 'user', 'content': 'Synthetic notes.'}],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'notes',
                'schema': {'type': 'object', 'properties': {name: {'type': 'string'} for name in property_names}},
            },
        },
    }
    forwarded = parse_forwarded_byok_headers(headers)
    source = CredentialSource.SERVICE_FORWARDED_BYOK if forwarded else CredentialSource.OMI_MANAGED
    caller = ServiceCaller(name='backend', user_uid='synthetic-owner')
    credentials = (
        build_byok_credential_context(caller, forwarded) if forwarded else build_omi_managed_credential_context(caller)
    )
    monkeypatch.setenv(ACTIVE_SECRET_ENV, 'synthetic-golden-fingerprint-seed-0001')
    monkeypatch.delenv(SECONDARY_SECRET_ENV, raising=False)
    ring = _KeyRing('synthetic-owner')

    expected_bytes, expected_digest = _GOLDEN[name]
    extracted = canonical_request(body, source.value, forwarded)
    assert extracted == expected_bytes
    assert Operation.canonical_request(body, credentials) == expected_bytes
    assert ring.fingerprint(ring.active_version, extracted) == expected_digest
