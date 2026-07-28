"""The prompt that renders a projection as an image.

The seam where the archetypal layer attaches. Today this passes the selected projection
through: the image already corresponds to the selected subject and carries its real
particulars, which is what makes it that person's rather than an illustration of a category.
What it does not yet carry is the register — the shared aesthetic package, the per-stage
composition recipe, and the archetypal palette and value structure that the stage owns.

Those are builder-authored and arrive with the stage layer. The split matters: the shared
package must hold only what stays invariant for a series to read as one series, because
anything else left in it gets spent on the model's default. Composition proved that once and
palette proved it again.
"""

from __future__ import annotations

from utils.projections.selector import SelectedSubject


def build_image_prompt(subject: SelectedSubject) -> str:
    """Render one selected subject as an image prompt."""
    return subject.projection
