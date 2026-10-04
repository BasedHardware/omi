"""General-path conversation titles name the identified people (#3602).

Rich meeting notes carry their own roster-based title rules. The general notes
path gets a static TITLE block (identical across conversations, so the cached
prefix is unchanged) and a volatile PEOPLE IN THIS CONVERSATION block naming the
non-owner people and the account owner from ``ConversationPromptPrefix``.
"""

from typing import Callable

from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix

GENERAL_TITLE_RULES = '''TITLE
- Write a specific headline of at most 10 words about the central topic or outcome.
- When PEOPLE IN THIS CONVERSATION lists people, name the one or two most central of them in the
  title, spelled exactly as listed (for example "Sarah and John Plan the Q2 Budget"). A first name
  alone is fine.
- Never put the account owner's name in the title; the note is theirs.
- Name nobody else in the title unless they are listed there or the transcript shows them introducing
  themselves or being addressed by name. Never invent or "correct" a name.'''


def general_title_static_instructions(format_instructions: str, legacy_static: Callable[[str], str]) -> str:
    """Insert the TITLE rules just before the parser schema, like the rich rules do."""
    base = legacy_static(format_instructions)
    if base.count(format_instructions) != 1:
        return f'{base}\n\n{GENERAL_TITLE_RULES}'
    return base.replace(format_instructions, f'{GENERAL_TITLE_RULES}\n\n{format_instructions}')


def title_people_block(prefix: ConversationPromptPrefix) -> str:
    """Name the identified people and the account owner for the TITLE rules."""
    if not prefix.title_people and not prefix.owner_names:
        return ''
    lines = ['PEOPLE IN THIS CONVERSATION']
    lines.extend(f'- {name}' for name in prefix.title_people)
    if prefix.owner_names:
        lines.append(f'- Account owner (never name them in the title): {", ".join(prefix.owner_names)}')
    return '\n'.join(lines)


def with_title_people(volatile_instructions: str, prefix: ConversationPromptPrefix) -> str:
    """Append the per-call people block to the general-path volatile suffix."""
    block = title_people_block(prefix)
    return f'{volatile_instructions}\n\n{block}' if block else volatile_instructions
