"""The image prompt, assembled as a typed graph with one owner per slot.

    Subject      the person's own situation — what is there, what is happening
    Action       carried by the projection's verb and by the arrangement's direction
    Environment  the real place and objects, from the selected subject's setting
    Style        global rendering metadata — `aesthetic.py`, and nothing else
    Lighting     derived from the emotional charge this week carries, not from the stage
    Details      the stage's archetypal motifs, attached to what is already in the scene

The typing is the fix. Before it, three layers all wrote to Subject — the register said
"depict a state of soul rather than the visible world", the stage's symbol arrived at full
strength as a black sun or a closed ring, and the person's actual situation came last as a
trailing clause — while **nothing at all wrote to Environment**. A projection about relocating
to Lisbon rendered a faceless figure inside a ring, with no Lisbon in it. Not a prompting
accident: the slot had no owner, and the loudest layer took the frame.

Keeping the archetype as schema rather than prescription is what lets it stay. It supplies the
form an image of this situation takes — where the figure sits, how it moves, what motif may
haunt the scene — and the person's week supplies everything the form is made of. That is
Jung's archetype-as-such against the archetypal image, expressed as a graph.

Lighting is measured rather than described: a dedicated pass rates the week against the Geneva
Emotion Wheel's twenty families and hands over the consolidated charge, with the selector's own
phrase as the person-specific gloss. Where they disagree the rating is authoritative — it is
the half that is averaged, logged and comparable across weeks.

What this slot deliberately does **not** carry is a colour. The evidence supports emotion
driving lightness and chroma and does not support it driving hue: hue's effect on valence is
not significant and reverses direction with saturation. So the charge is named and the mapping
is left to the image model rather than asserted by us. Encoding lightness and chroma
mechanically from the rated vector is a deferred follow-up, not a missing piece.
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
            f'SUBJECT — paint this, and nothing in place of it: {subject.projection}',
            (
                'SETTING — the real place it happens in. Keep it recognisable as itself; do not '
                f'replace it with a symbol or a generic version of it: {subject.setting}'
            ),
            f'STYLE: {AESTHETIC}',
            imagery.composition,
            (
                f'{imagery.symbol} These motifs may inflect what the scene already contains — '
                'attach them to the real place, objects and figures above. They must never '
                'replace the subject or the setting, and nothing here is the point of the image.'
            ),
            (
                'LIGHT AND COLOUR: what this carries for the person whose life it is, rated '
                f'against the Geneva Emotion Wheel, is {emotions.as_prompt_text()}. In their own '
                f'words it reads as {subject.tone}. Derive the key, the intensity and the '
                'direction and quality of the light from that charge and from nothing else. '
                'Commit to it — a neutral or evenly pleasant treatment is a failure, and so is '
                'any scheme chosen because it is what this subject is usually painted in.'
            ),
        ]
    )
