"""The Lighting slot's measurement: what this week actually carries, rated.

The image's light and colour follow the emotional charge of the material, not the narrative
stage — a stage cannot know whether someone is apprehensive or elated about the thing. This
module supplies the charge as a measurement rather than an impression, so it can be logged,
compared across weeks, and eventually mapped to a treatment mechanically.

WHY THE GENEVA EMOTION WHEEL. Of the candidate models, only the GEW and Cowen & Keltner's 27
categories ship a term inventory that was empirically placed rather than asserted; Ekman's six,
Plutchik's eight, OCC's twenty-two and PAD's three are theories with lists attached. The GEW
wins on two counts that matter here. It is an instrument, with an intensity scale and None/Other
escapes built in. And the largest cross-cultural colour-emotion study ever run — 4,598 people,
30 nations, 22 languages — used these exact 20 concepts as its emotion axis, so if a colour
mapping is ever encoded it will already share a coordinate system with the ratings.

WHY 20 AND NOT MORE. Rateability degrades measurably with inventory size, for humans and models
alike. GoEmotions gets only 31% of examples to three-of-five raters agreeing on any of 27
labels; GPT-4's zero-shot macro-F1 falls .739 -> .511 -> .375 from 7 to 11 to 28 classes; a 2026
replication finds accuracy against category count at r = -.965. Scherer capped the wheel's first
version at 16 families explicitly for legibility. 20 is a ceiling, not a target.

TWO PUBLISHED MITIGATIONS, both applied here rather than invented. Average several independent
completions — reported ~30% RMSE reduction on appraisal ratings — and never make the model rate
and do something else in the same call: adding label prediction to an appraisal task made the
appraisals worse. That is why this is a dedicated pass and not another field on the selector.

WHAT IS DELIBERATELY NOT DONE HERE. No colour is named. The evidence supports emotion driving
lightness and chroma and does not support it driving hue — hue's effect on valence is not
significant and reverses direction with saturation — so the vector is handed to the image model
as named charge, and the mapping stays where the evidence leaves it. The measurements and
limitations in this module-level rationale are the complete basis for that boundary; interpreting
the implementation does not depend on an external work ledger.

UNVERIFIED, and recorded rather than smoothed over: nobody has published GEW-20 rating accuracy
for an LLM, every rateability figure here is transferred from a differently-shaped task, and a
week of one person's own prose is out of distribution for all of them. The dispersion statistic
is recorded on every generation so this can be answered from our own data rather than assumed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field

from utils.executors import llm_executor
from utils.llm.clients import get_llm
from utils.llm.model_config import get_model

logger = logging.getLogger(__name__)

PROJECTION_EMOTIONS_FEATURE = 'projection_emotions'

# GEW 3.0: twenty families, ten positive and ten negative, ordered as the instrument lists them.
# Transcribed from the instrument documentation via the research note; the source flags that the
# term-level validation PDF could not be opened, so this list is reported rather than verified
# against the original. It agrees with the Jonauskaite corpus that used the same 20 concepts.
POSITIVE_FAMILIES: tuple[str, ...] = (
    'interest',
    'amusement',
    'pride',
    'joy',
    'pleasure',
    'contentment',
    'admiration',
    'love',
    'relief',
    'compassion',
)
NEGATIVE_FAMILIES: tuple[str, ...] = (
    'sadness',
    'guilt',
    'regret',
    'shame',
    'disappointment',
    'fear',
    'disgust',
    'contempt',
    'hate',
    'anger',
)
GEW_FAMILIES: tuple[str, ...] = POSITIVE_FAMILIES + NEGATIVE_FAMILIES

# The instrument's own scale: distance from the hub, 1 (faint) to 5 (strong), 0 for absent.
MAX_INTENSITY = 5.0

# Independent completions averaged per family. The published figure is five; the pass runs them
# on the shared LLM pool so the cost is one call's latency rather than five.
RATING_SAMPLES = 5

# A second family is kept only if it is nearly as strong as the first. Blends are real but a
# minority event — 84% of subjects report no simultaneous blend even after a bittersweet film —
# so the default is one term. PROVISIONAL: the literature says this fraction should come from
# the pipeline's own across-run dispersion, which is why `dispersion` is recorded on every
# generation. It is not a number the sources supply.
SECONDARY_SHARE = 0.8


class FamilyRating(BaseModel):
    family: str = ''
    intensity: float = 0.0


class RatedEmotions(BaseModel):
    ratings: list[FamilyRating] = Field(default_factory=list)
    none_apply: bool = False


@dataclass(frozen=True)
class EmotionProfile:
    """One week's charge, consolidated.

    `primary` is the argmax and is the term that may be cited and logged; `secondary` is kept
    only when it nearly matches. `dispersion` is the spread across independent completions on
    the primary family — a high value is a low-confidence week, and it is the statistic the
    secondary threshold should eventually be derived from.
    """

    primary: str
    secondary: Optional[str]
    intensity: float
    dispersion: float
    vector: dict[str, float]
    samples: int

    @property
    def is_empty(self) -> bool:
        return not self.primary

    def as_prompt_text(self) -> str:
        """The charge, named. Deliberately no colour: the mapping is not ours to assert."""
        if self.is_empty:
            return 'no clear emotional charge — the material is level rather than loaded'
        strength = f'{self.intensity:.1f} of {MAX_INTENSITY:.0f}'
        if self.secondary:
            return f'{self.primary} at {strength}, with {self.secondary} nearly as strong'
        return f'{self.primary} at {strength}'

    def as_metadata(self) -> dict[str, Any]:
        return {
            'feature': PROJECTION_EMOTIONS_FEATURE,
            'model': get_model(PROJECTION_EMOTIONS_FEATURE),
            'inventory': 'geneva_emotion_wheel_3.0',
            'primary': self.primary,
            'secondary': self.secondary,
            'intensity': round(self.intensity, 3),
            'dispersion': round(self.dispersion, 3),
            'samples': self.samples,
            'vector': {family: round(value, 3) for family, value in self.vector.items()},
        }


EMPTY_PROFILE = EmotionProfile(primary='', secondary=None, intensity=0.0, dispersion=0.0, vector={}, samples=0)


def rate_emotions(subject: str, evidence: Sequence[str], material: str) -> EmotionProfile:
    """Rate the twenty families for one subject, averaged over independent completions.

    Never raises: an image with an unrated charge is worse than one lit from the scene alone,
    but a failed rating pass is not a reason to refuse a projection that is otherwise grounded.
    """
    prompt = build_rating_prompt(subject, evidence, material)
    futures = [llm_executor.submit(_rate_once, prompt) for _ in range(RATING_SAMPLES)]
    samples = [result for result in (future.result() for future in futures) if result is not None]

    if not samples:
        logger.warning('emotion rating produced no usable samples for subject=%r', subject)
        return EMPTY_PROFILE
    return consolidate(samples)


def _rate_once(prompt: str) -> Optional[dict[str, float]]:
    try:
        response = get_llm(PROJECTION_EMOTIONS_FEATURE).with_structured_output(RatedEmotions).invoke(prompt)
    except Exception:  # noqa: BLE001 — one failed completion is averaged out, not fatal
        logger.warning('emotion rating completion failed', exc_info=True)
        return None

    rated = response if isinstance(response, RatedEmotions) else RatedEmotions.model_validate(response)
    if rated.none_apply:
        return {}
    return {
        rating.family.strip().lower(): max(0.0, min(MAX_INTENSITY, float(rating.intensity)))
        for rating in rated.ratings
        if rating.family.strip().lower() in GEW_FAMILIES
    }


def consolidate(samples: Sequence[dict[str, float]]) -> EmotionProfile:
    """Average the completions, take the argmax, and keep a secondary only if it nearly ties.

    The name and the treatment are not consolidated the same way on purpose: the name stays
    discrete because that is what can be cited, while the whole averaged vector is carried so a
    later treatment can use the gradient the argmax throws away.
    """
    vector = {family: sum(sample.get(family, 0.0) for sample in samples) / len(samples) for family in GEW_FAMILIES}
    ranked = sorted(vector.items(), key=lambda item: item[1], reverse=True)
    primary, intensity = ranked[0]

    if intensity <= 0.0:
        return EmotionProfile(
            primary='', secondary=None, intensity=0.0, dispersion=0.0, vector=vector, samples=len(samples)
        )

    secondary = None
    if len(ranked) > 1 and ranked[1][1] >= intensity * SECONDARY_SHARE:
        secondary = ranked[1][0]

    spread = [sample.get(primary, 0.0) for sample in samples]
    dispersion = max(spread) - min(spread)

    return EmotionProfile(
        primary=primary,
        secondary=secondary,
        intensity=intensity,
        dispersion=dispersion,
        vector=vector,
        samples=len(samples),
    )


def build_rating_prompt(subject: str, evidence: Sequence[str], material: str) -> str:
    families = '\n'.join(f'  {family}' for family in GEW_FAMILIES)
    cited = '\n'.join(f'- {item}' for item in evidence) or '- (none cited)'
    return '\n\n'.join(
        [
            (
                'Rate the emotional charge one thread carries for the person whose material this '
                'is. Rate what THEY feel about it, from how they actually speak about it — not '
                'how the situation would sound to someone else, and not how you feel reading it.'
            ),
            f'THE THREAD: {subject}',
            f'WHAT IT WAS SELECTED FROM:\n{cited}',
            (
                'Rate every one of these twenty emotion families on intensity from 1 to 5, where '
                '1 is barely present and 5 is strong. Give 0 to families that are not present. '
                'Return all twenty. Most weeks are dominated by one or two — do not spread the '
                'ratings to look balanced, and do not invent charge that is not in the words. If '
                'the material carries no real emotional charge, set none_apply and return no '
                'ratings; a level week is a real answer.'
            ),
            f'FAMILIES:\n{families}',
            f'THEIR MATERIAL:\n{material}',
        ]
    )
