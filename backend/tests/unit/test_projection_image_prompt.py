"""The image prompt a projection is rendered from.

Three layers compose it: the shared register, what the stage owns, and the person's own
situation. These tests pin the two properties that were bought by failure and are cheap to
lose again.

The first is that the register actually reaches the model. Run without it, the shipping
endpoint returned a stock travel advertisement containing a specific identifiable person —
`gpt-image-1` does not default to nothing, it defaults to advertising.

The second is that everything which can vary per stage does. Directives left in the shared
layer are spent on the model's default: ten stages sharing one composition came back as ten
runs of the same image, and a shared palette collapsed onto teal-and-gold with three of its
seven named colours never rendered at all.
"""

import pytest

from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.image_prompt import build_image_prompt
from utils.projections.selector import SelectedSubject
from utils.projections.stages import ProjectionStage

PROJECTION = 'the crossing already made, the known world receding behind without bitterness'


def _subject(stage: ProjectionStage) -> SelectedSubject:
    return SelectedSubject(
        subject='the move',
        stage=stage,
        projection=PROJECTION,
        imperative='The place you keep imagining is a decision, not a daydream.',
        evidence=('Circling the move again (2026-07-26)',),
    )


def test_every_stage_carries_its_own_imagery():
    # A stage the selector can return but the image layer has no directives for would render
    # as the model's default, which is the failure this layer exists to prevent.
    assert set(STAGE_IMAGERY) == set(ProjectionStage)
    for stage, imagery in STAGE_IMAGERY.items():
        assert imagery.symbol.startswith('SYMBOL:'), stage
        assert imagery.palette.startswith('PALETTE:'), stage
        assert imagery.value.startswith('VALUE:'), stage
        assert imagery.composition.startswith('COMPOSITION:'), stage


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_prompt_is_the_register_then_the_stage_then_this_persons_situation(stage):
    prompt = build_image_prompt(_subject(stage))
    imagery = STAGE_IMAGERY[stage]

    assert prompt.startswith(AESTHETIC)
    assert prompt.endswith(PROJECTION)
    for directive in (imagery.symbol, imagery.palette, imagery.value, imagery.composition):
        assert directive in prompt

    # Order matters as much as presence: the composition recipe ends by handing over to the
    # scene, so the person's own material has to be what follows it.
    assert prompt.index(imagery.composition) > prompt.index(imagery.symbol)
    assert prompt.index(PROJECTION) > prompt.index(imagery.composition)


@pytest.mark.parametrize('stage', list(ProjectionStage))
def test_the_presence_stays_identity_indeterminate_and_off_the_stock_register(stage):
    prompt = build_image_prompt(_subject(stage))

    assert 'identity-indeterminate dream presence' in prompt
    assert 'No readable face' in prompt
    assert 'lone figure facing a glowing portal' in prompt
    assert 'No text, lettering, numbers, logos, or watermarks.' in prompt


def test_no_two_stages_render_the_same_prompt():
    # The series gate: with the captions removed, ten images must not be interchangeable.
    prompts = {stage: build_image_prompt(_subject(stage)) for stage in ProjectionStage}
    assert len(set(prompts.values())) == len(ProjectionStage)


@pytest.mark.parametrize('colour', ['lapis', 'turquoise', 'emerald', 'violet', 'rose', 'gold', 'pearl'])
def test_every_colour_the_register_names_has_a_stage_that_owns_it(colour):
    # The palette fix, stated as a contract: a colour no stage is entitled to spend is a
    # colour that never gets rendered. Violet, rose and pearl-white were each at 0% while
    # the palette was shared.
    owning = [stage for stage, imagery in STAGE_IMAGERY.items() if colour in imagery.palette.lower()]
    assert owning, f'no stage claims {colour}'
