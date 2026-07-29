"""The image prompt, as a typed graph with one owner per slot.

These tests pin the typing, because every failure this layer has had was a slot with the wrong
owner or no owner at all.

Subject was written by three layers at once — the register, the stage's symbol, and the
person's own situation arriving last — and Environment was written by nobody, so a projection
about relocating to Lisbon rendered a faceless figure in a ring with no Lisbon in it. Lighting
was owned by the stage's alchemical operation, so the same subject came out in institutional
greys because the *stage* was refusal, regardless of what the person felt about the thing.

What is tested here is therefore ownership: the person's situation and place reach the model
ahead of everything else and intact, the archetypal layer arrives explicitly demoted to
inflection, light is derived from the charge this week carries, and the register still governs
how any of it is painted.
"""

import pytest

from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.image_prompt import build_image_prompt
from utils.projections.selector import SelectedSubject
from utils.projections.stages import ProjectionStage

PROJECTION = 'you send the message you have been drafting for a week, and the room goes quiet'
SETTING = 'the tiled kitchen in Lisbon at first light, the laptop open beside a cold coffee'
TONE = 'apprehension with something exhilarated underneath it'


def _subject(stage: ProjectionStage) -> SelectedSubject:
    return SelectedSubject(
        subject='the move',
        stage=stage,
        projection=PROJECTION,
        setting=SETTING,
        tone=TONE,
        imperative='The place you keep imagining is a decision, not a daydream.',
        evidence=('Circling the move again (2026-07-26)',),
    )


def test_every_stage_carries_its_own_form():
    # A stage the selector can return but the image layer has no form for would fall back to
    # the model's default arrangement, which is the failure this layer exists to prevent.
    assert set(STAGE_IMAGERY) == set(ProjectionStage)
    for stage, imagery in STAGE_IMAGERY.items():
        assert imagery.symbol.startswith('SYMBOL:'), stage
        assert imagery.composition.startswith('COMPOSITION:'), stage
        # Light left this layer when it moved to the tone axis; a stage that starts dictating
        # colour again is the collapse returning.
        assert 'PALETTE' not in imagery.composition and 'PALETTE' not in imagery.symbol, stage


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_persons_situation_and_place_lead_the_prompt(stage):
    prompt = build_image_prompt(_subject(stage))

    assert prompt.startswith('SUBJECT')
    assert PROJECTION in prompt
    assert SETTING in prompt
    # The scene and the place are stated before the register and before anything archetypal;
    # arriving last is how the situation lost the frame.
    assert prompt.index(SETTING) < prompt.index(AESTHETIC)
    assert prompt.index(SETTING) < prompt.index(STAGE_IMAGERY[stage].symbol)


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_archetypal_layer_arrives_demoted_to_inflection(stage):
    imagery = STAGE_IMAGERY[stage]
    prompt = build_image_prompt(_subject(stage))
    inflection = prompt[prompt.index(imagery.symbol) :]

    assert imagery.composition in prompt
    assert 'may inflect' in inflection
    assert 'must never replace the subject or the setting' in inflection


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_light_is_derived_from_the_charge_this_week_carries(stage):
    prompt = build_image_prompt(_subject(stage))
    lighting = prompt[prompt.index('LIGHT AND COLOUR') :]

    assert TONE in lighting
    assert 'from that charge and from nothing else' in lighting


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_register_still_governs_how_it_is_painted(stage):
    prompt = build_image_prompt(_subject(stage))

    assert AESTHETIC in prompt
    assert 'identity-indeterminate dream presence' in prompt
    assert 'No readable face' in prompt
    # Depicting a real city is an invitation to the exact failure this feature already shipped
    # once: a stock travel advertisement.
    assert 'Do not make a travel poster' in prompt
    assert 'No text, lettering, numbers, logos, or watermarks.' in prompt


def test_the_register_no_longer_forbids_the_visible_world():
    # The clause that produced an image of relocating to Lisbon with no Lisbon in it.
    assert 'rather than the visible world' not in AESTHETIC
    assert 'must remain recognisable' in AESTHETIC


def test_no_two_stages_render_the_same_prompt():
    # The series gate: with the captions removed, ten images must not be interchangeable.
    prompts = {stage: build_image_prompt(_subject(stage)) for stage in ProjectionStage}
    assert len(set(prompts.values())) == len(ProjectionStage)
