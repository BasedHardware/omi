"""Owner-involved commitments, conservative social-intent admission and contradiction policy.

The notes packet remains the sole extractor. This module supplies its task rules
and deterministic post-extraction policy; it never calls another model.
"""

import re
from collections.abc import Mapping

from config.action_item_extraction_policy import (
    clearly_other_owner,
    clearly_status,
    normalized_name,
    UNKNOWN_OWNERS,
    OWNER_ALIASES,
)
from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.calls_metrics import observe

FLAG_ENV = 'ACTION_ITEMS_V2_MODE'
FLAG = FLAG_ENV
RULES = '''ACTION ITEM EXTRACTION RULES (owner-involved commitments)
- Extract commitments made by the account owner, requests accepted by the owner,
  and explicit offers/promises by another person to the owner. Keep the actual
  promisor in owner_name; describe the recipient in context. Use clear_commitment
  for a concrete promise or offer. Do not assign another person's work to the owner.
- An offer to review the owner's document, forward a contact, or share an invite is
  actionable even though the owner is the recipient. Unrelated third-party tasks
  and observations/status statements are not actionable.
- Omit vague social small talk unless a responsible person or committed time is
  concrete, or a named counterpart is paired with a specific place or time
  (such as "catch up with Matt in NYC"). A suggestion alone is not a commitment.
  Never invent an owner or date.
- Preserve exact source_segment_ids and source conversation identity. Unknown voices
  stay unknown; contact lists and calendar rosters do not establish voice identity.
- Do not promote uncertain remarks to decisions or invent numbers or durations.
'''


def rules_for(uid, legacy_rules):
    # A new prompt serves only the cohort. Shadow never adds an LLM call.
    return RULES if serving_for(FLAG, uid) else legacy_rules


def field(item, key):
    return item.get(key) if isinstance(item, Mapping) else getattr(item, key, None)


def explicit_offer_to_owner(item, profile_name):
    if field(item, 'capture_kind') != 'clear_commitment' or not profile_name:
        return False
    context = str(field(item, 'context') or '')
    # Require a stated offer AND a named beneficiary. Mere name co-occurrence
    # ("ask the owner to do my task") cannot override the other-owner guard.
    name = re.escape(normalized_name(profile_name).split()[0])
    return bool(
        re.search(r'\b(?:offer(?:ed|s)?|promis(?:e|ed|es))\b', context, re.I)
        and re.search(r'\b(?:to|for)\s+(?:the account owner|' + name + r')\b', context, re.I)
    )


def vague_social(item):
    text = str(field(item, 'description') or '')
    social = re.search(r'\b(?:hiking|hang out|catch up|meet up|grab (?:coffee|lunch)|get together)\b', text, re.I)
    if not social or field(item, 'due_at'):
        return False
    owner = normalized_name(field(item, 'owner_name'))
    concrete_owner = owner not in UNKNOWN_OWNERS | OWNER_ALIASES and not re.fullmatch(r'(?:speaker|spk)\s*\d+', owner)
    committed = field(item, 'capture_kind') in ('clear_commitment', 'direct_request', 'explicit_command')
    # A named counterpart plus a concrete place/time grounds the owner's own
    # commitment too; owner aliases must not make that incident-09 item disappear.
    context = text + ' ' + str(field(item, 'context') or '')
    counterpart = re.search(r'\bwith\s+([A-Z][\w\'-]*(?:\s+[A-Z][\w\'-]*){0,2})\b', context)
    named_counterpart = bool(
        counterpart
        and normalized_name(counterpart.group(1)) not in UNKNOWN_OWNERS | OWNER_ALIASES | {'speaker', 'spk'}
        and not re.fullmatch(r'(?:speaker|spk)\s*\d+', counterpart.group(1), re.I)
    )
    specific_place = re.search(r'\b(?:in|at)\s+[A-Z][\w\'-]*(?:\s+[A-Z][\w\'-]*)*\b', context)
    specific_time = re.search(
        r'\b(?:today|tomorrow|tonight|next\s+(?:week|weekend|month|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'|(?:on\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r'|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{4}-\d{2}-\d{2})\b',
        context,
        re.I,
    )
    # A known speaker discussing a hypothetical outing is still small talk.
    return not (concrete_owner and committed or named_counterpart and (specific_place or specific_time))


def select_items(uid, items, legacy, profile_name):
    if not shadow_or_serve(FLAG):
        return legacy
    selected = [
        item
        for item in items
        if not clearly_status(field(item, 'description'))
        and not vague_social(item)
        and (
            not clearly_other_owner(field(item, 'owner_name'), profile_name)
            or explicit_offer_to_owner(item, profile_name)
        )
    ]
    observe('action_admission', 'agree' if selected == legacy else 'disagree')
    return selected if serving_for(FLAG, uid) else legacy


def contradicted_capture(item, conversation):
    """Exact evidence binding, never fuzzy matching a call title or person name.

    capture_gap_conversation_id is an optional producer assertion about WHICH
    recording was reported missing. Without it, stale detection abstains.
    """
    if not item.get('capture_gap_conversation_id') or item['capture_gap_conversation_id'] != conversation.id:
        return None
    if not conversation.is_call or not conversation.transcript_segments:
        return None
    if item.get('completed') or item.get('status', 'active') != 'active':
        return None
    return {
        'stale': True,
        'stale_reason': 'referenced_call_capture_exists',
        'status': 'cancelled',
        'stale_evidence_conversation_id': conversation.id,
    }


def instructions_for(uid, instructions):
    """Swap only the task block on the existing notes mount; no second extractor."""
    from utils.llm.conversation_notes_prompts import ACTION_ITEM_EXTRACTION_RULES

    selected = instructions.replace(ACTION_ITEM_EXTRACTION_RULES, rules_for(uid, ACTION_ITEM_EXTRACTION_RULES))
    if serving_for(FLAG, uid):
        selected = selected.replace(
            'conservative filter and emit only explicit commitments the owner made, or nothing.',
            'conservative filter and emit only explicit commitments by or for the owner, or nothing.',
        )
    return selected
