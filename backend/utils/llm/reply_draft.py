"""
Reply drafting — compose a message the USER can send to a specific person, in the
user's own voice, using the per-person profile (relationship, tone) + facts + the
recent thread. Returns a draft string only; nothing is ever sent automatically.
"""

import logging
from typing import List, Optional

from database import memories as memories_db
from database.entities import person_entity_id
from utils.llm.clients import get_llm
from utils.llm.local_shim import local_cli_llm_text
from utils.retrieval.tool_services.person_service import resolve_person

logger = logging.getLogger(__name__)


def draft_reply(uid: str, person_ref: str, thread: List[dict], intent: Optional[str] = None) -> dict:
    person = resolve_person(uid, person_ref)
    name = (person or {}).get('name') or person_ref
    relationship = (person or {}).get('relationship')
    summary = (person or {}).get('profile_summary')
    tone = (person or {}).get('tone_notes')

    facts = []
    if person:
        try:
            facts = memories_db.get_memories_by_subject_entity(uid, person_entity_id(person['id']), limit=15)
        except Exception as e:
            logger.warning(f"reply_draft: facts lookup failed uid={uid}: {e}")
    facts_text = "\n".join(f"- {f.get('content')}" for f in facts if f.get('content'))

    thread_lines = []
    for m in (thread or [])[-25:]:
        text = (m.get('text') or '').strip()
        if not text:
            continue
        who = 'You' if m.get('is_from_me') else name
        thread_lines.append(f"{who}: {text}")
    thread_text = "\n".join(thread_lines) or "(no recent messages)"

    context_bits = []
    if relationship:
        context_bits.append(f"{name} is the user's {relationship}.")
    if summary:
        context_bits.append(summary)
    if tone:
        context_bits.append(f"How the user usually texts {name}: {tone}")
    if facts_text:
        context_bits.append(f"Facts about {name}:\n{facts_text}")
    context_text = "\n".join(context_bits) or "(no extra context)"

    intent_line = f"The user wants the reply to: {intent}\n" if intent else ""

    prompt = (
        f"You are drafting a text message reply the USER will send to {name}. "
        f"Write it in the USER's own voice, matching how they normally text {name} "
        f"(tone, length, emoji). Make it natural and ready to send as-is. "
        f"Output ONLY the message text — no quotes, labels, or explanations.\n\n"
        f"CONTEXT:\n{context_text}\n\n"
        f"{intent_line}"
        f"RECENT CONVERSATION:\n{thread_text}\n\n"
        f"Draft the user's reply to {name}:"
    )

    draft = local_cli_llm_text(prompt)
    if draft is None:
        response = get_llm('memories').invoke(prompt)
        draft = (response.content if hasattr(response, 'content') else str(response)).strip()
    draft = draft.strip()
    # Strip a wrapping pair of quotes if the model added them.
    if len(draft) >= 2 and draft[0] in "\"'" and draft[-1] == draft[0]:
        draft = draft[1:-1].strip()
    return {'draft': draft}
