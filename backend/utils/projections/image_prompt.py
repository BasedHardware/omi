"""The image prompt, assembled as a typed graph with one owner per slot.

    Subject      the person's own situation — what is there, what is happening
    Action       carried by the projection's verb and by the arrangement's direction
    Environment  the real place and objects, from the selected subject's setting
    Style        global rendering metadata — `aesthetic.py`, and nothing else
    Lighting     stage-owned palette/value structure, personally inflected by emotional charge
    Details      the stage's archetypal motifs, attached to what is already in the scene

The typing prevents multiple layers from competing for Subject while Environment has no owner.
The selected situation and recognisable setting stay explicit; symbolic form can inflect them
but cannot replace them.

Keeping the archetype as schema rather than prescription is what lets it stay. It supplies the
form an image of this situation takes — where the figure sits, how it moves, what motif may
haunt the scene — and the person's week supplies everything the form is made of. That is
Jung's archetype-as-such against the archetypal image, expressed as a graph.

Lighting has two non-overlapping owners. The stage supplies the palette and value structure.
A dedicated pass rates the week against the Geneva Emotion Wheel's twenty families and
supplies personal inflection inside those bounds: intensity, edge energy, and light direction
and quality.
"""

from __future__ import annotations

from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.emotions import EMPTY_PROFILE, EmotionProfile
from utils.projections.selector import SelectedSubject


def build_image_prompt(subject: SelectedSubject, emotions: EmotionProfile = EMPTY_PROFILE) -> str:
    """Render one selected subject as an image prompt."""
    imagery = STAGE_IMAGERY[subject.stage]
    return '\n\n'.join(
        [
            f'STYLE — binding rendering contract: {AESTHETIC}',
            (
                'PALETTE AND VALUE — binding stage optics, validated as part of the series: '
                f'{imagery.palette} {imagery.value}'
            ),
            f'SUBJECT — depict this, and nothing in place of it: {subject.projection}',
            (
                'SETTING — the real place it happens in. Keep it recognisable as itself; do not '
                f'replace it with a symbol or a generic version of it: {subject.setting}'
            ),
            imagery.composition,
            (
                f'{imagery.symbol} These motifs may inflect what the scene already contains — '
                'attach them to the real place, objects and figures above. They must never '
                'replace the subject or the setting, and nothing here is the point of the image.'
            ),
            (
                'EMOTIONAL INFLECTION — what this carries for the person whose life it is, rated '
                f'against the Geneva Emotion Wheel, is {emotions.as_prompt_text()}. In their own '
                f'words it reads as {subject.tone}. Express that charge within that palette and '
                'value structure through intensity, edge energy, and the direction and quality '
                'of the light; never replace its hue range or tonal hierarchy. Commit to the '
                'charge — a neutral or evenly pleasant treatment is a failure.'
            ),
            (
                'FINAL RENDERING CHECK — line carries form and translucent wash carries '
                'atmosphere. Keep contours hairline, tapered and calligraphic; keep every wash '
                'thin, luminous and subordinate to those contours. A dense composition may '
                'contain many forms, but must not become equal-weight surface noise. If the '
                'surface reads as thick oil paint, wax crayon, colored-pencil hatching or '
                'impressionist daubs, redraw it. Keep recognisable objects subordinate to the '
                'psychological geometry; do not turn them into foreground product illustration '
                'or a literal still life.'
            ),
        ]
    )
