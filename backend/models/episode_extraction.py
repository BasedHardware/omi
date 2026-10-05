"""Episode-only extraction metadata, loaded after the notes flag is enabled."""

from typing import List, Literal

from pydantic import BaseModel, Field

from models.structured import NoteClaim, Structured  # type: ignore[reportAttributeAccessIssue]  # Runtime SDK/fallback export.
from models.structured_extraction import RichStructuredExtraction


class ExtractedNoteClaim(BaseModel):
    """Generation supplies bindings; source metadata is exclusively server authored."""

    text: str = Field(description='Short unique exact factual anchor in target; binds its sentence/bullet')
    target: str = Field(description='JSON pointer to visible field')
    evidence_ids: List[str]
    provenance: Literal['said', 'shown', 'written', 'inferred']


class EpisodeStructuredExtraction(RichStructuredExtraction):
    """Additive claim metadata; only the episode flag selects this schema."""

    note_claims: List[ExtractedNoteClaim] = Field(
        default_factory=list,
        description='One binding per factual sentence/bullet; split for differing sources',
    )

    def to_structured(self) -> Structured:
        structured = super().to_structured()
        structured.note_claims = [NoteClaim(**claim.model_dump()) for claim in self.note_claims]
        return structured
