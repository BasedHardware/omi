"""The voice a projection speaks in, carried by example rather than by instruction.

AUTHORSHIP BOUNDARY. `REGISTER` and `EXEMPLARS` are product-authored voice assets. Nothing
here may be casually rewritten, extended, or paraphrased as infrastructure cleanup; changing
the voice is a product-design decision.

Why exemplars rather than an instruction about tone: a described voice arrives as adjectives
the model averages away. Ten concrete lines transfer the thing itself, and they were
selected under a declared scoring gate rather than by taste after the fact.

The shape those ten actually have: seven of the ten are two
clipped units — a call to action and the observation that justifies it, in either order — and
**three carry no action verb at all**. That is why the selection gate tests whether a line is
grounded in the evidence, never whether it contains an instruction.
"""

from __future__ import annotations

from typing import NamedTuple

# Product-authored description of the voice.
REGISTER = (
    "It speaks as an I-Ching reading would: sometimes obscure, sometimes on the nose, in "
    "symbolic language, with more specificity than a fortune cookie. If an action is implied, "
    "include a call to action. This is symbolic dream imagery in Carl Jung's sense — not "
    "newspaper astrology."
)


class Exemplar(NamedTuple):
    stage: str
    projection: str
    imperative: str


# Ten product-authored pairs that transfer the voice by example.
EXEMPLARS: tuple[Exemplar, ...] = (
    Exemplar(
        stage='reward',
        projection=(
            'completion as release. The long burden is set down and closed. The soul is no '
            'longer asking the finished work to justify its existence, and the space that '
            'asking occupied has opened up'
        ),
        imperative='The work counts because you finished it, not because it justified you.',
    ),
    Exemplar(
        stage='refusal',
        projection=(
            'the refusal of the call in the moment before it breaks. Safety is still being '
            'held, and authorship, risk and aliveness have already begun pulling the ordinary '
            'world out of shape. Not wealth, status, an office or triumph — the inner '
            'threshold itself. The call and the fear of answering it in one motion'
        ),
        imperative='Build the thing that is yours. The safe version was never actually safe.',
    ),
    Exemplar(
        stage='threshold',
        projection=(
            'the inner crossing into an unfamiliar life. The imagined elsewhere stops being a '
            'daydream and becomes a decision already acted on, with the known world receding '
            'behind without bitterness'
        ),
        imperative='The place you keep imagining is a decision, not a daydream.',
    ),
    Exemplar(
        stage='road_back',
        projection=(
            'leaving a vast, beautiful, self-built imagined world in order to return to a '
            'small real one. The invented place was genuinely magnificent and was practice; '
            'the ordinary surface waiting below is where the thing actually gets made'
        ),
        imperative='You already know the world you built is practice. Come back and ship.',
    ),
    Exemplar(
        stage='resurrection',
        projection=(
            'the moment of committing to one possibility and letting the other selves go. '
            'What is released is not destroyed — the unchosen remain whole and intact — but '
            'only the chosen one continues, and the refusal to choose was the real death'
        ),
        imperative='Choosing one does not kill the others. Refusing to choose does.',
    ),
    Exemplar(
        stage='elixir',
        projection=(
            'handing over something personal and unmistakably one\'s own for other people to '
            'find. The safe version would have concealed exactly the quality that makes it '
            'worth seeing; the imperfection is the signature'
        ),
        imperative='Ship the one that sounds like you. The safe one hides the thing worth seeing.',
    ),
    Exemplar(
        stage='approach',
        projection=(
            'clearing the ground before the difficult thing. A weight that has been sitting '
            'in the room for twelve days is finally sealed and set aside, and the space it '
            'occupied stops pressing'
        ),
        imperative='Twelve days. Put it in the box today and get the weight off the room.',
    ),
    Exemplar(
        stage='ordeal',
        projection=(
            'the difficult truth in the instant after it is spoken and survived. The silence '
            'that was costing more than the conversation has released its grip, and what was '
            'taut between the two has opened rather than broken'
        ),
        imperative='Say the thing. The silence is costing more than the conversation will.',
    ),
    Exemplar(
        stage='call',
        projection=(
            'a summons with a closing deadline arriving from far off. The unfinished thing '
            'sent imperfectly is the only version that exists; the finished one that is never '
            'sent does not'
        ),
        imperative='It closes tomorrow. Send it unfinished rather than not at all.',
    ),
    Exemplar(
        stage='tests',
        projection=(
            'the deferred connections turning out to be the substance rather than the '
            'overhead. Many separate relationships, each at a different distance and a '
            'different degree of tension, all of them live and none of them resolved'
        ),
        imperative='The follow-ups you keep deferring are the whole opportunity.',
    ),
)


def _normalize(line: str) -> str:
    return ' '.join(line.lower().split()).strip(' .')


EXEMPLAR_LINES: frozenset[str] = frozenset(
    _normalize(line) for exemplar in EXEMPLARS for line in (exemplar.imperative, exemplar.projection)
)


def is_exemplar(line: str) -> bool:
    """Whether `line` is one of the exemplars reproduced rather than answered.

    Few-shot examples get copied. Observed on the first real run: the model selected one
    subject and shipped another exemplar's imperative beside it, marking it grounded. An
    instruction not to copy is not enforcement, so the check lives here.
    """
    return _normalize(line) in EXEMPLAR_LINES


def exemplars_as_prompt_text() -> str:
    """Render the exemplars as finished readings belonging to other people.

    Not as `projection:`/`imperative:` pairs keyed like the requested output fields — that
    formatting made the block read as a bank of options, and the first real run returned four
    candidates whose imperatives were all copied from it verbatim.
    """
    lines = [f'{index}. "{exemplar.imperative}"' for index, exemplar in enumerate(EXEMPLARS, start=1)]
    return '\n'.join(lines)
