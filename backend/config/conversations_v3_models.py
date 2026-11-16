"""New gateway-only features; never change the legacy route fingerprint."""

from utils.llm.model_constants import LUNA_MODEL

FEATURES = {
    'conversation_v3_outline': (LUNA_MODEL, 'openai'),
    'conversation_v3_summary': (LUNA_MODEL, 'openai'),
    'conversation_v3_summary_open': (LUNA_MODEL, 'openai'),
}
