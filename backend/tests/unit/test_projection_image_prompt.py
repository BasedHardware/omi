"""The image prompt, as a typed graph with one owner per slot.

These tests pin the typing because a slot with the wrong owner lets symbolic form displace the
owner's actual situation or lets unbounded lighting collapse the series into a generic treatment.

What is tested here is ownership and priority: the product rendering contract leads; the owner's
situation and place reach the model intact; the archetypal layer is demoted to inflection; bounded
stage optics constrain rather than replace personal charge; and the register governs rendering.
"""

import pytest

from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.image_prompt import build_image_prompt
from utils.projections.selector import SelectedSubject
from utils.projections.stages import ProjectionStage

PROJECTION = 'you send the proposal you have been drafting for a week, and the room goes quiet'
SETTING = 'the quiet desk at first light, the marked-up draft beside a cold coffee'
TONE = 'apprehension with something exhilarated underneath it'


def _subject(stage: ProjectionStage) -> SelectedSubject:
    return SelectedSubject(
        subject='the unfinished proposal',
        stage=stage,
        projection=PROJECTION,
        setting=SETTING,
        tone=TONE,
        imperative='Name the decision you keep postponing.',
        evidence=('conversation:conv-1',),
    )


def test_every_stage_carries_its_own_form():
    # A stage the selector can return but the image layer has no form for would fall back to
    # the model's default arrangement, which is the failure this layer exists to prevent.
    assert set(STAGE_IMAGERY) == set(ProjectionStage)
    for stage, imagery in STAGE_IMAGERY.items():
        assert imagery.symbol.startswith('SYMBOL:'), stage
        assert imagery.palette.startswith('PALETTE:'), stage
        assert imagery.value.startswith('VALUE:'), stage
        assert imagery.composition.startswith('COMPOSITION:'), stage


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_rendering_contract_leads_without_displacing_the_persons_situation(stage):
    prompt = build_image_prompt(_subject(stage))

    assert prompt.startswith('STYLE — binding rendering contract')
    assert PROJECTION in prompt
    assert SETTING in prompt
    assert 'SUBJECT — depict this' in prompt
    assert 'paint this' not in prompt
    # The register must lead so the model reads it as a binding rendering contract rather than
    # late decorative guidance.
    assert prompt.index(AESTHETIC) < prompt.index(PROJECTION)
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
def test_personal_charge_inflects_without_replacing_the_validated_stage_optics(stage):
    imagery = STAGE_IMAGERY[stage]
    prompt = build_image_prompt(_subject(stage))
    optics = prompt[prompt.index('PALETTE AND VALUE') :]

    assert imagery.palette in optics
    assert imagery.value in optics
    assert TONE in optics
    assert 'within that palette and value structure' in optics
    assert 'never replace its hue range or tonal hierarchy' in optics


def test_ordeal_keeps_its_bounded_optical_contract():
    prompt = build_image_prompt(_subject(ProjectionStage.ORDEAL))

    assert 'near-monochrome black, bitumen and cold ash' in prompt
    assert 'exactly one hot arterial rose-red' in prompt
    assert 'the widest contrast in the series and the deepest true blacks' in prompt
    assert prompt.index('PALETTE AND VALUE') < prompt.index('SUBJECT')


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_register_still_governs_how_it_is_painted(stage):
    prompt = build_image_prompt(_subject(stage))

    assert AESTHETIC in prompt
    assert 'identity-indeterminate dream presence' in prompt
    assert 'No readable face' in prompt
    # A recognisable place must not collapse into a stock travel advertisement.
    assert 'Do not make a travel poster' in prompt
    assert 'No text, lettering, numbers, logos, or watermarks.' in prompt


def test_the_register_rejects_the_painterly_failure_mode():
    prompt = build_image_prompt(_subject(ProjectionStage.CALL))

    assert 'finely controlled, miniature-like contours' in prompt
    assert 'thick impasto, broad impressionist daubs' in prompt
    rendering_check = prompt[prompt.index('FINAL RENDERING CHECK') :]
    assert 'line carries form and translucent wash carries atmosphere' in rendering_check
    assert 'colored-pencil hatching' in rendering_check
    assert 'recognisable objects subordinate to the psychological geometry' in rendering_check


def test_the_register_no_longer_forbids_the_visible_world():
    assert 'rather than the visible world' not in AESTHETIC
    assert 'must remain recognisable' in AESTHETIC


def test_no_two_stages_render_the_same_prompt():
    # The series gate: with the captions removed, ten images must not be interchangeable.
    prompts = {stage: build_image_prompt(_subject(stage)) for stage in ProjectionStage}
    assert len(set(prompts.values())) == len(ProjectionStage)
