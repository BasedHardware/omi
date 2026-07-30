"""The Style slot: how the image is rendered, never what it contains.

In the prompt's graph this is global transformation metadata — the register, the mark, the
treatment of any human presence, and the negative list. Nothing here may name a subject, a
place, or a light, because those slots have their own owners and a global layer that writes
to them overrides the owner's actual situation.

AUTHORSHIP. This product-owned register is an art-direction asset, not infrastructure prose.
Preserve its texture and slot ownership when changing the pipeline; revise it only as an
explicit product-design change.

Two clauses are load-bearing rather than stylistic. The identity-indeterminate presence is a
property of any human entity in the graph — it is what stops the artifact being a picture of
somebody else, the disqualifying failure this register was written to fix. The negative list
is what keeps `gpt-image-1` off advertising stock when the subject includes a recognisable place.
"""

from __future__ import annotations

AESTHETIC = (
    "A vertical painting in a specific register: Persian miniature transformed into "
    "spiritual expressionism. Depict the real situation described above — its actual place, "
    "objects and hour must remain recognisable — and render it as a state of soul rather than "
    "as documentary fact. "
    "Persian-miniature precision released into atmospheric dissolution — tapered, "
    "accelerating calligraphic contour that lets categories transform into one another, "
    "hair into smoke, fabric into water, branches into nervous systems. Jewel-like detail "
    "coexisting with translucent washes. Use finely controlled, miniature-like contours "
    "alongside translucent atmospheric washes rather than thick, blunt, or uniformly loose "
    "brushwork. Space is psychological rather than optical: within a place that stays "
    "recognisable, scale, gravity and perspective bend according to spiritual importance. "
    "Colour is iridescent and prismatic, carrying an emotional state rather than describing "
    "surfaces; the specific palette and light for this image are given below and must be "
    "obeyed exactly rather than averaged toward a default. "
    "Elongated, weightless presences. Detailed yet dreamlike, sensual yet devotional, "
    "turbulent yet geometrically harmonious, tragic yet beautiful. "
    "Represent any human presence only as a recognizably humanoid but "
    "identity-indeterminate dream presence: shadowed, faceless, and partially dissolving "
    "into the surrounding motion. No readable face, skin tone, hair texture, age, "
    "gender-coded anatomy, culturally specific clothing, or portrait likeness. Gesture, "
    "scale, position and motion must carry the emotion. "
    "Do not make generic Western fantasy concept art, decorative Persian pastiche, Art "
    "Nouveau pastiche, storybook illustration, a cinematic poster, or a literal "
    "motivational illustration. Do not make a travel poster, a tourist postcard, or an "
    "advertisement for the place. No synthetic glow, plastic skin, or airbrushed smoothness. "
    "Do not use thick impasto, broad impressionist daubs, flat cel shading, or photorealistic "
    "rendering. "
    "Do not use the stock image of a lone figure facing a glowing portal. "
    "No text, lettering, numbers, logos, or watermarks. "
)
