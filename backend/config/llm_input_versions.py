"""Explicit prompt versions for the notes and L1 reuse keys.

The reuse key used to hash about 35 source files, so any deploy that touched one
of them voided every stored notes/L1 hash and re-bought unchanged input. The key
now carries one explicit version per feature instead.

Bump the version when a change can change the model's output for the same input:
prompt text, output schema, or the deterministic shaping that feeds the prompt.
`tests/unit/test_llm_input_prompt_version.py` pins a digest of the prompt sources
per version and fails when they change without a bump, so a missed bump is a red
test rather than stale notes in production.

Model routing and installed pydantic/langchain-core versions are included
independently at runtime and always invalidate reuse when they change.
Do not bump for changes that cannot change the output (logging, metrics, client
construction): those must not re-buy anything.
"""

from __future__ import annotations

NOTES_PROMPT_VERSION = 'notes-3'
L1_PROMPT_VERSION = 'l1-1'

PROMPT_VERSIONS: dict[str, str] = {
    'notes': NOTES_PROMPT_VERSION,
    'l1': L1_PROMPT_VERSION,
}


def prompt_version(feature: str) -> str:
    """The explicit prompt version for a reuse-keyed feature; unknown features fail closed."""
    try:
        return PROMPT_VERSIONS[feature]
    except KeyError:
        raise ValueError(f'No prompt version registered for feature: {feature}') from None
