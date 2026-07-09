from __future__ import annotations

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import (
    BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES,
    BYOK_UNSUPPORTED_PROVIDER_FAILURE,
    build_byok_credential_context,
    build_key_reference_credential_context,
    build_omi_managed_credential_context,
    is_byok_failure_class,
    is_fallback_eligible_by_default,
    parse_forwarded_byok_headers,
)
from llm_gateway.gateway.schemas import CredentialMode, CredentialPolicy, FailureClass


def test_omi_managed_credential_context_has_no_provider_keys():
    context = build_omi_managed_credential_context(ServiceCaller(name='backend'))

    assert context.mode == CredentialMode.OMI_PAID
    assert context.provider_keys == {}
    assert not context.has_provider_key('openai')


def test_byok_credential_context_exposes_presence_without_raw_keys():
    raw_secret = 'sk-super-secret'
    context = build_byok_credential_context(
        ServiceCaller(name='backend', user_uid='user-123'),
        {'openai': raw_secret, 'anthropic': '', 'gemini': None},
    )

    assert context.mode == CredentialMode.BYOK
    assert context.has_provider_key('openai')
    assert not context.has_provider_key('anthropic')
    assert not context.has_provider_key('gemini')
    assert raw_secret not in repr(context)
    assert raw_secret not in str(context.safe_model_dump())
    assert raw_secret not in context.model_dump_json()
    assert context.forwarded_key_for('openai') == raw_secret


def test_parse_forwarded_byok_headers_extracts_provider_keys():
    forwarded = parse_forwarded_byok_headers(
        {
            'X-Omi-Byok-OpenAI-Key': ' sk-openai ',
            'X-Omi-Byok-Anthropic-Key': 'sk-ant',
            'Authorization': 'Bearer service',
        }
    )

    assert forwarded == {'openai': 'sk-openai', 'anthropic': 'sk-ant'}


def test_key_reference_credential_context_exposes_references_not_raw_keys():
    context = build_key_reference_credential_context(
        ServiceCaller(name='pusher'),
        {'openai': 'secret-manager://projects/omi/secrets/openai-user-123'},
    )

    dumped = context.safe_model_dump()
    assert context.has_provider_key('openai')
    assert dumped['provider_keys']['openai']['present'] is True
    assert dumped['provider_keys']['openai']['key_ref'] == 'secret-manager://projects/omi/secrets/openai-user-123'


def test_key_reference_credential_context_rejects_whitespace_only_ref():
    context = build_key_reference_credential_context(
        ServiceCaller(name='pusher'),
        {'openai': '   '},
    )

    assert not context.has_provider_key('openai')


def test_byok_failure_classes_are_visible_and_not_fallback_eligible_by_default():
    policy = CredentialPolicy(
        mode=CredentialMode.BYOK,
        allow_byok_to_omi_paid_fallback=False,
        fallback_eligible_failure_classes=[
            FailureClass.TIMEOUT_BEFORE_OUTPUT,
            FailureClass.BYOK_AUTH,
            FailureClass.BYOK_QUOTA,
            FailureClass.BYOK_RATE_LIMIT,
            FailureClass.MISSING_BYOK_KEY,
        ],
        never_fallback_failure_classes=[],
    )

    for failure_class in BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES:
        assert is_byok_failure_class(failure_class)
        assert not is_fallback_eligible_by_default(failure_class, policy)

    assert BYOK_UNSUPPORTED_PROVIDER_FAILURE in BYOK_DEFAULT_VISIBLE_FAILURE_CLASSES


def test_omi_paid_policy_keeps_non_byok_fallbacks_visible():
    policy = CredentialPolicy(
        mode=CredentialMode.OMI_PAID,
        allow_byok_to_omi_paid_fallback=False,
        fallback_eligible_failure_classes=[
            FailureClass.TIMEOUT_BEFORE_OUTPUT,
            FailureClass.PROVIDER_429_OMI_PAID,
            FailureClass.PROVIDER_5XX_OMI_PAID,
        ],
        never_fallback_failure_classes=[FailureClass.INVALID_CONFIG],
    )

    assert is_fallback_eligible_by_default(FailureClass.TIMEOUT_BEFORE_OUTPUT, policy)
    assert is_fallback_eligible_by_default(FailureClass.PROVIDER_429_OMI_PAID, policy)
    assert is_fallback_eligible_by_default(FailureClass.PROVIDER_5XX_OMI_PAID, policy)
    assert not is_fallback_eligible_by_default(FailureClass.INVALID_CONFIG, policy)
