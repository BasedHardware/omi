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

NOTES_PROMPT_VERSION = 'notes-8'
# notes-8 makes the notes agent's first submission final and cites seg1..segN aliases that are
# restored to segment ids before validation (notes-agent-v10). Wording can differ for the same
# input; a stored notes-7 summary is still a valid summary of it, so notes-7 stays reusable.
# notes-7 only defaults a missing participants[].source when stored rows are read back
# (models/structured.py); prompt, schema and output are unchanged, so notes-6 checkpoints
# stay reusable and nothing is re-bought.
# notes-6 adds the v3 (recordings and conversations) notes path: its own model,
# low effort and bounded personal context, all behind v3_models.active(). Output
# for every non-v3 conversation is unchanged, so notes-5 checkpoints stay reusable.
# Unchanged notes-4 checkpoints are filtered locally, not invalidated by the
# quality prompt. Retain the earlier unscaled notes-3 alias.
NOTES_REUSABLE_PREVIOUS_VERSIONS = ('notes-7', 'notes-6', 'notes-5', 'notes-4')
NOTES_UNSCALED_PREVIOUS_VERSION = 'notes-3'
L1_PROMPT_VERSION = 'l1-1'

# Route-source digests (``llm_input_dedupe.routing_digest``) declared to leave every notes and L1
# route unchanged: {today's digest: earlier digests it is compatible with}. Stored work keyed under a
# listed earlier digest is reused, not bought again. The claim holds only for the exact digest it is
# keyed by, so any later route edit drops it until someone re-declares it for the new digest.
COMPATIBLE_ROUTING_DIGESTS: dict[str, tuple[str, ...]] = {
    # Adds only the interim_summary (Quick Summary) lane to utils/llm/model_config.py.
    'b0fee83d05d68e0d5f23dd07cbe732bf7ceaab0ec9b02632c4c8b26f99528fe6': (
        'f2b6c4c57af68c1e606b96e001a69919a5e34fb642126273209dff3d39ecb7b6',
    ),
}

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
