from utils.memory_ingestion.ids import StableIdFactory
from utils.memory_ingestion.redaction import redact_text


def _categories_for(text: str) -> list[str]:
    _, redactions = redact_text(
        text,
        source_event_id="event-1",
        id_factory=StableIdFactory("test"),
        hmac_key="redaction-test-key",
    )
    return [redaction.category for redaction in redactions]


def test_redacts_stripe_style_api_key():
    redacted, redactions = redact_text(
        "OCR shows sk_live_1234567890abcdef API key.",
        source_event_id="event-1",
        id_factory=StableIdFactory("test"),
        hmac_key="redaction-test-key",
    )

    assert redactions[0].category == "api_key"
    assert redactions[0].value_hash
    assert "sk_live_1234567890abcdef" not in redacted
    assert "[REDACTED_API_KEY]" in redacted


def test_redacts_one_time_code_phrase():
    redacted, redactions = redact_text(
        "My one-time code is 123456.",
        source_event_id="event-1",
        id_factory=StableIdFactory("test"),
        hmac_key="redaction-test-key",
    )

    assert redactions[0].category == "one_time_code"
    assert "123456" not in redacted
    assert "[REDACTED_ONE_TIME_CODE]" in redacted


def test_redacts_partial_pem_private_key_header():
    assert _categories_for("-----BEGIN PRIVATE KEY-----") == ["private_key"]
