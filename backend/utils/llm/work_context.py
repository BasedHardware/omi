"""Recently observed work context, rendered from synced context bucket facts.

The facts are extracted from the user's own screen activity on their devices and
already passed device-side validation. See `docs/agents/context-buckets.md` for
the capture/sync boundary.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

WORK_CONTEXT_FACT_LIMIT = 20
WORK_CONTEXT_MINIMUM_CONFIDENCE = 0.6


def sanitize_prompt_text(value: str) -> str:
    """Neutralize markup and line structure before the text enters the prompt.

    Escaping angle brackets stops a fact from closing its own block, but the
    text originates from whatever was on screen — including a page an attacker
    controls. Left with newlines it can still open a new line in the system
    prompt and impersonate an instruction, so the whole value is collapsed onto
    one line and control characters are dropped.
    """

    collapsed = ' '.join(value.split())
    escaped = collapsed.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return ''.join(character for character in escaped if character.isprintable())


def get_work_context_section(uid: str, user_name: Optional[str]) -> str:
    """Render the user's recently observed work as a prompt block.

    Chat must never fail because this optional context is unavailable, so every
    failure degrades to an empty section.
    """

    try:
        import database.account_cutover as account_cutover_db
        import database.context_buckets as context_buckets_db

        account_generation = account_cutover_db.get_account_cutover_record(uid).account_generation
        facts = context_buckets_db.list_context_facts(
            uid,
            account_generation=account_generation,
            minimum_confidence=WORK_CONTEXT_MINIMUM_CONFIDENCE,
            limit=WORK_CONTEXT_FACT_LIMIT,
        )
    except Exception as error:
        logger.warning(f"work context unavailable for prompt assembly: {error}")
        return ""

    if not facts:
        return ""

    owner = user_name or "the user"
    fact_lines = "\n".join(f"- {sanitize_prompt_text(fact.statement)}" for fact in facts)
    return f"""<work_context>
Recently observed on {owner}'s devices:
{fact_lines}
This is background awareness of what they have been working on. Use it when it is
relevant, and never recite it back or imply you were watching them.
</work_context>

"""


__all__ = [
    'WORK_CONTEXT_FACT_LIMIT',
    'WORK_CONTEXT_MINIMUM_CONFIDENCE',
    'get_work_context_section',
    'sanitize_prompt_text',
]
