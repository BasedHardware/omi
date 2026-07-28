"""What each stage contributes to the image, and why it is the stage that owns it.

Everything here varies per stage, which is the whole point: the shared register in
`aesthetic.py` carries only what must stay invariant, and anything else left there is spent on
the model's default. Two failures established that. Composition was shared once, and ten
different psychological moments came back as ten runs of the same tarot card. Palette and value
were shared after that, and a measured audit found two collapses — 63% of chromatic pixels on
the lapis/turquoise axis, no pixel above 0.90 value in ten images, and violet, rose and
pearl-white never rendered at all.

Each stage therefore carries six things:

    archetype    the Jungian figure constellated at that point of individuation
    operation    the alchemical operation Jung read as its psychic analogue
    symbol       concrete motifs with real symbolic pressure, in place of feeling-words
    palette      the colours this stage is entitled to, and which are forbidden
    value        the tonal structure — where the darks and the highlights live
    composition  figure placement, count, motion, focal geometry, density, depth

`archetype` and `operation` are not sent to the model. They are the reason the other four say
what they say, and they are kept beside them so that changing a palette means first disagreeing
with the operation it follows from. The alchemical sequence is what gave every named colour an
owning stage with a reason to be spent: pearl-white to the *albedo* (Reward), rose to the
*rubedo* (Return), violet to the *coniunctio* (Resurrection), and the full prismatic seven to
the *cauda pavonis* (Tests), the one stage where iridescent multiplicity is doctrinally correct
rather than decorative.

TWO HONEST SEAMS, recorded rather than smoothed over.

1. Jung did not write the Hero's Journey; Campbell did, drawing on Jung. Jung's own model is
   individuation, which spirals and repeats rather than advancing through numbered stations.
   Mapping one onto the other is translation and the seams are real. The alchemical sequence
   (nigredo -> albedo -> citrinitas -> rubedo) is the load-bearing correspondence and lands
   cleanly on Ordeal -> Reward -> Resurrection -> Return; the earlier stages are looser.

2. An archetype is not a person's life. Jung distinguished the archetype-as-such — an empty
   formal disposition that cannot be represented — from the archetypal image, which is that
   form filled with personal material. This module supplies form. The personal material arrives
   as the selected subject's own projection, appended after the composition recipe.

AUTHORSHIP. The strings ship byte-identical to the prototype run that cleared the declared
7-of-10 gate at 9-of-10, with the composition recipes byte-identical to the baseline before it.
That verdict is evidence about these strings and no others; an agent rewording them for tone or
concision discards the measurement and keeps the appearance of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.projections.stages import ProjectionStage


@dataclass(frozen=True)
class StageImagery:
    archetype: str
    operation: str
    symbol: str
    palette: str
    value: str
    composition: str

    def as_prompt_text(self) -> str:
        """The four directives that reach the model, in the order they were validated in."""
        return f'{self.symbol} {self.palette} {self.value} {self.composition}'


STAGE_IMAGERY: dict[ProjectionStage, StageImagery] = {
    ProjectionStage.CALL: StageImagery(
        archetype=(
            "The Herald — a content of the unconscious constellating for the first time, "
            "arriving as if from outside because it is not yet owned"
        ),
        operation="the prima materia noticed at last: base matter that was always present and never seen",
        symbol=(
            "SYMBOL: the summons that comes from far off and belongs to the one who "
            "receives it. A single messenger form crossing an enormous distance. The "
            "ordinary world rendered as undifferentiated, unremarkable matter, with one "
            "intrusion into it that does not belong and cannot be unseen. Nothing is "
            "answered yet; the whole image is the arrival of a question."
        ),
        palette=(
            "PALETTE: the ordinary world in dulled, desaturated, near-neutral earth and "
            "stone, deliberately drab. The intruding summons carries the only saturated "
            "colour in the frame — a narrow band of restrained gold and pale citrine. "
            "No turquoise, no teal, no lapis dominance anywhere."
        ),
        value=(
            "VALUE: the field flat and mid-toned by intention, with a small area of "
            "genuine brightness at the point of arrival — the brightest thing in the "
            "frame occupies less than a tenth of it. Strong local contrast, low global "
            "contrast."
        ),
        composition=(
            "COMPOSITION: a single presence small and peripheral at the lower edge of the "
            "frame, dwarfed by what is arriving. The motion is diagonal and descending, "
            "entering from the upper distance and reaching down toward the figure — a "
            "summons, not yet an answer. Focal weight sits high and off-centre, far from "
            "the figure; the vast diagonal gap between them is the subject. Deep, airy "
            "negative space in the lower two-thirds. A far break of light and one "
            "long-travelling messenger form carry the arrival. The figure has not moved. "
            "The scene: "
        ),
    ),
    ProjectionStage.REFUSAL: StageImagery(
        archetype=(
            "The Persona defending its position — regression in the service of safety, the "
            "ego declining the encounter it can already feel coming"
        ),
        operation=(
            "the sealed vessel before heat is applied; the temenos, the protective sacred " "circle, misused as a cell"
        ),
        symbol=(
            "SYMBOL: an enclosure that was built for protection and is now a prison, and "
            "the two cannot be told apart from inside. Repeating, orderly, handsome "
            "pattern forming a closed ring. A seam in that ring where something bright "
            "presses through and is turned back. The refusal is not cowardice; it is the "
            "old form holding its shape."
        ),
        palette=(
            "PALETTE: cold, dulled, institutional greys, slate and dry ochre in the "
            "enclosing pattern — handsome and lifeless. A single seam of suppressed "
            "violet-rose light at the point of pressure, small and losing. Forbid "
            "turquoise and teal entirely."
        ),
        value=(
            "VALUE: compressed and airless on purpose — no highlight anywhere, because "
            "refusal is the absence of illumination. The narrowest tonal range of any "
            "image in the series."
        ),
        composition=(
            "COMPOSITION: a single presence held centrally but enclosed — ringed and pressed "
            "by orderly, repeating, grey-blue geometry that behaves like a room, a rhythm, or "
            "a habit. The motion is circular but contained: a bright current strains outward "
            "from inside the figure and is turned back by the enclosing band. Dense at the "
            "perimeter, tight and airless; almost no open negative space. The pressure runs "
            "outward while the figure's own posture leans back. Nothing has broken yet. "
            "The scene: "
        ),
    ),
    ProjectionStage.THRESHOLD: StageImagery(
        archetype=(
            "The Threshold Guardian — the last figure that can still be mistaken for an " "obstacle rather than a gate"
        ),
        operation="solutio, the dissolving of the solid into the solution that will carry it",
        symbol=(
            "SYMBOL: a boundary crossed at the exact instant of crossing. Two orders of "
            "reality meeting along a hard seam — paired uprights, a bank and a water, a "
            "gate whose far side obeys different laws. One presence in transit, already "
            "dissolving slightly into the far side's substance. The guardian is the "
            "boundary itself, not a monster."
        ),
        palette=(
            "PALETTE: genuinely and unmistakably bicolour — the near half in warm dry "
            "gold, amber and bone, the far half in deep lapis and violet, meeting at a "
            "hard vertical seam with no blending. This is the one image permitted a split "
            "palette, and the two halves must not share a hue."
        ),
        value=(
            "VALUE: the two halves also differ in key — the near half light and dry, the "
            "far half deep and saturated. Contrast concentrated along the seam."
        ),
        composition=(
            "COMPOSITION: a single presence caught mid-transit across a vertical division at "
            "the centre of the frame. The motion is decisively horizontal and forward, left to "
            "right, with no backward pull. The frame is split into two unlike halves that do "
            "not share a palette or a weather; the threshold itself is made of the same "
            "calligraphic current as the far side, so the crossing reads as continuous rather "
            "than as a doorway. One carried bundle. Migratory forms travel the same vector. "
            "The near half recedes without becoming a prison. The scene: "
        ),
    ),
    ProjectionStage.TESTS: StageImagery(
        archetype=(
            "The Trickster and the fragmented company — the psyche appearing as many partial "
            "figures, none of them the whole"
        ),
        operation=(
            "cauda pavonis, the peacock's tail: the iridescent multiplicity that appears when "
            "the single mass separates"
        ),
        symbol=(
            "SYMBOL: many presences at many distances, none dominant, some drawn close and "
            "some barely held. Masks, doubles, and partial figures that will not resolve "
            "into a single company. Fine threads of unequal tension connecting them. No "
            "centre and no hierarchy — the difficulty is the multiplicity itself."
        ),
        palette=(
            "PALETTE: the full prismatic range at once and deliberately unresolved — lapis, "
            "turquoise, emerald, violet, rose, gold and pearl in shifting iridescence, like "
            "oil on water or a peacock's tail. This is the ONLY image entitled to the whole "
            "seven-colour range simultaneously; every hue must be locatable somewhere."
        ),
        value=(
            "VALUE: busy and evenly lit, with many small competing highlights and no single "
            "dominant light source. Deliberately hard to rest the eye on."
        ),
        composition=(
            "COMPOSITION: several presences at markedly different distances and scales, the "
            "central one no larger than the others. The motion radiates and disperses outward "
            "in many directions at once, along fine taut threads that connect the presences "
            "unevenly — some drawn close, some barely held. Radial focal geometry with high "
            "density and deliberately little negative space; the frame is busy and populated. "
            "Distant warm lights at the ends of the threads. No single dominant subject. "
            "The scene: "
        ),
    ),
    ProjectionStage.APPROACH: StageImagery(
        archetype=(
            "The Shadow, approached but not yet met — the descent begun voluntarily, which is "
            "what distinguishes it from being dragged"
        ),
        operation="the entry into nigredo; the night sea journey, the swallowing",
        symbol=(
            "SYMBOL: a descent that narrows. A cave mouth, a throat, a stair going down, "
            "an aperture that admits less the further in it goes. Things shed and left "
            "along the way, deliberately abandoned rather than lost. The light thinning "
            "with depth. The figure goes in of its own accord."
        ),
        palette=(
            "PALETTE: progressive desaturation with depth — muted umber, cold slate and "
            "bituminous brown-black draining toward the aperture, with the last warmth "
            "surviving only at the outer edge of the frame. No jewel tones, no turquoise."
        ),
        value=(
            "VALUE: a strong gradient from a dim outer edge to genuine darkness at the "
            "centre. The second-darkest image in the series, and the darkness must read "
            "as depth rather than as shadow cast on a surface."
        ),
        composition=(
            "COMPOSITION: a single presence seen from behind, approaching and receding from "
            "the viewer, moving into a narrowing dark aperture. The motion converges and "
            "funnels inward and downward along a deep perspective corridor. Focal geometry is "
            "a shrinking tunnel; heavy negative space surrounds a dark, low-luminance centre "
            "that the whole frame drains toward. Shed and abandoned forms lie along the "
            "approach, left behind rather than carried. The light thins as it goes in. "
            "The scene: "
        ),
    ),
    ProjectionStage.ORDEAL: StageImagery(
        archetype=(
            "The Shadow met — the death of the ego's position, which Jung insisted is "
            "experienced as an actual dying and not as a metaphor"
        ),
        operation=("mortificatio, the nigredo proper: putrefaction, dismemberment, the sol niger or " "black sun"),
        symbol=(
            "SYMBOL: the black sun — a source of darkness where light should be. Two "
            "presences at the point where something between them must break. A single "
            "wound of red. Dismemberment and blackening. This is the bottom of the whole "
            "series and must look like it; nothing here is consoling, and nothing here is "
            "pretty."
        ),
        palette=(
            "PALETTE: near-monochrome black, bitumen and cold ash, with exactly one hot "
            "arterial rose-red admitted at the wound and nowhere else. This is where rose "
            "first enters the series. Forbid gold, turquoise, emerald and any decorative "
            "iridescence absolutely."
        ),
        value=(
            "VALUE: the widest contrast in the series and the deepest true blacks — "
            "genuine black, not dark blue — against one small hot point. The eye must "
            "have exactly one place to go."
        ),
        composition=(
            "COMPOSITION: two presences facing one another across the centre of the frame, "
            "held at maximum tension, close to symmetrical opposition. The motion is ruptured "
            "rather than flowing: a single taut line strains between them and, at the point "
            "of breaking, opens into flight and warm prismatic light instead of snapping. "
            "Density is greatest exactly at the centre, between them; the outer frame is "
            "quiet. Their gestures show vulnerability and attention — not romance, not "
            "confrontation. This is the survived moment, not the fight. The scene: "
        ),
    ),
    ProjectionStage.REWARD: StageImagery(
        archetype=(
            "The Treasure Hard to Attain, and the first clear glimpse of the Self — what is "
            "recovered from the nigredo rather than won by force"
        ),
        operation="albedo, the whitening: the washing, the lunar light that follows the blackening",
        symbol=(
            "SYMBOL: the pearl, the moon, white water, the dove, the white rose. What was "
            "retrieved is small and is held or set down without display. Stillness after "
            "violence. The quality is washed, rinsed, and lunar rather than triumphant — "
            "this is relief and clarity, not victory."
        ),
        palette=(
            "PALETTE: pearl-white, silver, moonlit grey and the palest blue-white, with "
            "restraint everywhere else. This is the ONLY image whose dominant colour is "
            "pearl-white, and it must genuinely dominate. Forbid gold and saturated "
            "turquoise."
        ),
        value=(
            "VALUE: the highest-key image in the entire series and the only one permitted "
            "true highlights — luminous near-white passages that read as actual light. If "
            "no part of this image approaches white, it has failed."
        ),
        composition=(
            "COMPOSITION: a single presence central, still, and at rest, having just set "
            "something down. The motion is decelerating — a wide, slow circular current "
            "settling toward stillness, the only stage where nothing is straining. Balanced, "
            "centred focal geometry with generous open negative space above the figure, and "
            "first light entering from a low angle. Closed and completed forms, and forms at "
            "rest that were previously in flight. Empty hands. Relief without triumph. "
            "The scene: "
        ),
    ),
    ProjectionStage.ROAD_BACK: StageImagery(
        archetype=(
            "Enantiodromia — the turn back toward the ordinary, and the inflation that "
            "threatens anyone who tries to stay in the luminous place"
        ),
        operation="the descent from the mountain; the treasure discovered to be heavy",
        symbol=(
            "SYMBOL: the backward glance. A luminous, elaborate region above, and plain "
            "ordinary matter below, with a presence moving downward and away while its "
            "weight still leans back toward what it is leaving. The upper world dissolves "
            "into the lower without a seam. What is carried is visibly heavy."
        ),
        palette=(
            "PALETTE: a vertical drain — silver and pale luminous blue in the upper field "
            "giving out into dry bone, grey and plain earth below. Colour literally runs "
            "out toward the bottom of the frame. No saturated hue survives the descent."
        ),
        value=(
            "VALUE: a strong vertical gradient, high-key above and mid-key below. The "
            "brightness is real but is being left behind."
        ),
        composition=(
            "COMPOSITION: a single presence retreating away from a luminous, elaborate region "
            "that fills the upper field, moving down and back toward a plain, ordinary, "
            "sparsely rendered lower field. The motion is descending and reluctant, with the "
            "body's weight still angled toward what it is leaving. The beautiful upper region "
            "dissolves at its lower edge into the plain surfaces beneath it, softly and "
            "without a seam. Ornamental density above, near-emptiness below. The scene: "
        ),
    ),
    ProjectionStage.RESURRECTION: StageImagery(
        archetype=(
            "The divine child and the constellated Self — rebirth as a genuinely new form "
            "rather than the restoration of the old one"
        ),
        operation=(
            "citrinitas passing into the coniunctio: the yellowing dawn, and the union of "
            "opposites that produces something neither parent was"
        ),
        symbol=(
            "SYMBOL: one presence separating into what dies and what continues, both fully "
            "present in the same instant. Sunrise, the phoenix, the tree breaking into "
            "leaf, the child. Below, unopened forms remaining whole and undestroyed. The "
            "old form is not defeated; it is completed and let go."
        ),
        palette=(
            "PALETTE: citrine and pale gold breaking upward, meeting deep lapis and "
            "resolving into true violet where they meet — violet is the colour of the "
            "union of opposites and must be plainly visible here. This is the ONLY image "
            "where violet is a principal colour."
        ),
        value=(
            "VALUE: dawn contrast — a genuinely luminous upper field against a still-dark "
            "lower one, with the transition legible as a horizon rather than a blur."
        ),
        composition=(
            "COMPOSITION: one presence divided into two aspects of itself — a continuing form "
            "and a dissolving form separating along a strong vertical axis. The motion "
            "ascends and disperses at the same time: the dissolving aspect scatters outward "
            "and the continuing aspect rises. The upper half of the frame clears as it goes. "
            "Below, intact unopened forms remain whole and undisturbed, none of them "
            "destroyed. A single line of green ascent. This is loss and continuation in one "
            "gesture. The scene: "
        ),
    ),
    ProjectionStage.ELIXIR: StageImagery(
        archetype=(
            "The Self realised, and the wounded healer — the one who returns is only useful "
            "because of what the descent cost"
        ),
        operation=(
            "rubedo, the reddening: the stone completed, spirit made flesh, the tincture that " "works on others"
        ),
        symbol=(
            "SYMBOL: the red rose, the cup, the shared bread, the stone. Something made is "
            "set down on a plain surface where others will find it, and the maker is "
            "already turning away. It is visibly imperfect and visibly the work of one "
            "pair of hands. The gift is ordinary and it works."
        ),
        palette=(
            "PALETTE: warm and embodied — deep rose, madder red, terracotta and full-bodied "
            "gold, the warmest image in the series. Rose is the dominant colour and must "
            "read as arrival rather than as wound. Forbid cold blues and turquoise "
            "entirely."
        ),
        value=(
            "VALUE: full and resolved — real darks, real lights, and a comfortable mid "
            "range, in raking low light. The only image whose tonal range is simply "
            "complete rather than pushed to an extreme."
        ),
        composition=(
            "COMPOSITION: a single presence peripheral and turned away at the edge of the "
            "frame, offering something outward into a wide, open field where other presences "
            "are implied but not detailed. The focal point is the made object itself, set "
            "down on a plain surface in raking light — not the figure. The motion is "
            "horizontal and outward, away from the maker. Low density, open horizon, calm "
            "wide negative space. The object is visibly imperfect and visibly personal. "
            "The scene: "
        ),
    ),
}
