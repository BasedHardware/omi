"""Episode-only extraction metadata, loaded after the notes flag is enabled."""

from typing import List

from pydantic import Field

from models.structured import NoteClaim, Structured
from models.structured_extraction import RichStructuredExtraction


class EpisodeStructuredExtraction(RichStructuredExtraction):
    """Additive claim metadata; only the episode flag selects this schema."""

    note_claims: List[NoteClaim] = Field(
        default_factory=list, description='Provenance for every visible factual clause'
    )

    def to_structured(self) -> Structured:
        structured = super().to_structured()
        structured.note_claims = self.note_claims
        return structured
