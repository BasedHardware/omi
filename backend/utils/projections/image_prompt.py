"""The prompt that renders a projection as an image.

Three layers, in the order they were validated in:

    AESTHETIC                    the shared register — invariant across the series
    the stage's symbol,          what this stage owns: archetype made concrete, and the
    palette, value, composition  palette and tonal structure that follow from it
    the subject's projection     this person's actual situation, appended as the scene

The split is the finding, not a filing convention. Anything left in the shared layer that
could have varied gets spent on the model's default: composition proved it once and palette
and value proved it again, both measured. So this module composes and owns nothing —
`aesthetic.py` holds what must not vary, `archetypes.py` holds what must.

Without the first two layers this is what shipped from the first real end-to-end run: a stock
travel advertisement carrying a chat bubble, with a specific identifiable person in it.
`gpt-image-1` does not default to nothing, it defaults to advertising. The register is not
decoration on top of a working feature; it is the difference between the artifact and an
illustration of the artifact.
"""

from __future__ import annotations

from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.selector import SelectedSubject


def build_image_prompt(subject: SelectedSubject) -> str:
    """Render one selected subject as an image prompt."""
    return AESTHETIC + STAGE_IMAGERY[subject.stage].as_prompt_text() + subject.projection
