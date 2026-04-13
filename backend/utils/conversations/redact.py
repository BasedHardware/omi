"""Locked-content redaction for conversations.

Centralizes the field-stripping logic that was previously copy-pasted
across 5+ routers with inconsistent behavior.
"""

from typing import Dict, List


def redact_conversation_for_list(conv: Dict) -> Dict:
    """Standard list-view redaction: strip detail fields, keep title/overview.

    Used by: conversations list, MCP list, MCP SSE list.
    """
    if not conv.get('is_locked', False):
        return conv
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    return conv


def redact_conversation_for_integration(conv: Dict) -> Dict:
    """Integration-view redaction: strip everything including title/overview.

    Used by: third-party app integrations (more aggressive than standard).
    """
    if not conv.get('is_locked', False):
        return conv
    if 'structured' in conv:
        conv['structured'] = (
            dict(conv['structured']) if not isinstance(conv['structured'], dict) else conv['structured']
        )
        conv['structured']['title'] = ''
        conv['structured']['overview'] = ''
        conv['structured']['action_items'] = []
        conv['structured']['events'] = []
    conv['apps_results'] = []
    conv['plugins_results'] = []
    conv['suggested_summarization_apps'] = []
    conv['transcript_segments'] = []
    return conv


def redact_conversations_for_list(conversations: List[Dict]) -> List[Dict]:
    """Apply standard list redaction to a batch of conversations."""
    return [redact_conversation_for_list(c) for c in conversations]


def redact_conversations_for_integration(conversations: List[Dict]) -> List[Dict]:
    """Apply integration redaction to a batch of conversations."""
    return [redact_conversation_for_integration(c) for c in conversations]
