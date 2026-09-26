"""Injectable summarize callables. Production code is never imported by default."""

from __future__ import annotations

from collections.abc import Callable

from testing.summary_lab.fixtures import Fixture
from testing.summary_lab.variants import Variant

Note = dict[str, object]
SummarizeFn = Callable[[Fixture, Variant], Note]


class MissingRecordedNote(KeyError):
    """Fixture has no recorded note for this variant."""


def recorded_seam(fixture: Fixture, variant: Variant) -> Note:
    """Hermetic default: return the fixture's recorded note for the variant."""
    note = fixture.recorded.get(variant.recorded_key)
    if note is None:
        raise MissingRecordedNote(f'{fixture.id} has no recorded note {variant.recorded_key!r}')
    return dict(note)


def production_notes_v2_seam(fixture: Fixture, variant: Variant) -> Note:
    """Opt-in live path. Imports production only when this function is called."""
    del variant
    from utils.llm.conversation_processing import get_conversation_notes
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix
    from datetime import datetime

    started = datetime.fromisoformat(fixture.started_at)
    prefix = build_conversation_prompt_prefix(
        conversation_id=f'synthetic-{fixture.id}',
        transcript=fixture.transcript,
        started_at=started,
        timezone_name=fixture.timezone,
        language_code=fixture.language,
    )
    structured = get_conversation_notes(
        prefix,
        started_at=started,
        language_code=fixture.language,
        output_language_code=fixture.language,
        tz=fixture.timezone,
        task_intelligence_capture=False,
    )
    return structured.model_dump()
