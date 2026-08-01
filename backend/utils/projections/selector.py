"""What a projection is about.

One LLM pass over the evidence packet ranks the person's open threads by **emotional charge**
and, for each, writes the imagery of the future state and the line that ships beside it.
Ranking is not filtered beforehand: the heaviest material always gets first refusal.

The gate is applied to the output instead. The top-ranked candidate ships only if its
imperative is **grounded in the evidence** — and that is decided here, in deterministic code,
rather than taken on the model's word: a candidate must cite evidence, not merely claim it.
When the top candidate fails, the next one is taken and **the fall-through is recorded**.
Those records are the only honest way to find out later whether charge alone was sufficient.

The gate deliberately does not test whether the line contains an instruction. Three of the ten
product-authored exemplars carry no action verb, so an actionability test would reject a third
of the target register. See `register.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, Field

from utils.llm.clients import get_llm
from utils.llm.model_config import get_model
from utils.projections.errors import NoProjectionSubject
from utils.projections.evidence import EvidencePacket, EvidenceTier
from utils.projections.register import REGISTER, exemplars_as_prompt_text, is_exemplar
from utils.projections.stages import STAGE_NAMES, ProjectionStage

logger = logging.getLogger(__name__)

PROJECTION_SUBJECT_FEATURE = 'projection_subject'

# Enough candidates for the gate to have somewhere to fall, few enough that the model spends
# its effort on the top of the ranking rather than padding the tail.
MAX_CANDIDATES = 4

# How many previously shown projections the pass is told about, so a series reads as one
# voice tracking one person rather than as independent draws.
MAX_PREVIOUS = 3


class SubjectCandidate(BaseModel):
    """The wire shape. Deliberately permissive — malformed candidates fall through the gate
    rather than failing the whole generation."""

    subject: str = ''
    stage: str = ''
    projection: str = ''
    setting: str = ''
    tone: str = ''
    imperative: str = ''
    evidence: list[str] = Field(default_factory=list)
    grounded: bool = False


class RankedSubjects(BaseModel):
    candidates: list[SubjectCandidate] = Field(default_factory=list)


@dataclass(frozen=True)
class SelectedSubject:
    """One projection, typed by the slot each field fills in the image graph.

    `projection` is Subject and Action — what is happening and what is about to. `setting` is
    Environment, the real place and objects it happens in. `tone` is Lighting, the emotional
    charge the light and colour have to carry. Nothing else may write to those three slots.
    """

    subject: str
    stage: ProjectionStage
    projection: str
    setting: str
    tone: str
    imperative: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class SubjectSelection:
    subject: SelectedSubject
    metadata: dict[str, Any]


def select_subject(
    packet: EvidencePacket,
    *,
    previous: Optional[Sequence[Mapping[str, Any]]] = None,
) -> SubjectSelection:
    """Select what one projection is about, or raise `NoProjectionSubject`.

    Raises rather than returning a placeholder in both refusal cases — an empty corpus, and a
    set of candidates where none is grounded. Generating anyway would produce exactly the
    evidence-free artifact this surface exists to replace.
    """
    if packet.tier is EvidenceTier.EMPTY:
        raise NoProjectionSubject('no evidence to select a projection from')

    previous = list(previous or [])
    prompt = build_selection_prompt(packet, previous=previous)

    response = get_llm(PROJECTION_SUBJECT_FEATURE).with_structured_output(RankedSubjects).invoke(prompt)
    candidates = _as_candidates(response)

    rejections: list[str] = []
    for index, candidate in enumerate(candidates):
        selected, reason = _admit(candidate, packet)
        if selected is None:
            rejections.append(reason or 'rejected')
            continue
        return SubjectSelection(
            subject=selected,
            metadata={
                'feature': PROJECTION_SUBJECT_FEATURE,
                'model': get_model(PROJECTION_SUBJECT_FEATURE),
                'prompt': prompt,
                'selected_at': datetime.now(timezone.utc),
                'signals': packet.signal_summary(),
                'candidates_considered': len(candidates),
                'fell_through': index,
                'fell_through_reasons': rejections,
                'previous_projection_ids': [str(item.get('id') or '') for item in previous],
            },
        )

    # The reasons matter more than the count: a run where every candidate was rejected for the
    # same cause is a prompt defect, and without them it looks like the corpus was simply thin.
    logger.warning(
        'projection selection produced no admissible candidate: considered=%d reasons=%s',
        len(candidates),
        rejections,
    )
    raise NoProjectionSubject(
        f'no candidate of {len(candidates)} was grounded in the evidence ({", ".join(rejections) or "none returned"})'
    )


def _admit(candidate: SubjectCandidate, packet: EvidencePacket) -> tuple[Optional[SelectedSubject], str]:
    """Apply the output gate. Returns `(None, reason)` for a candidate that does not survive."""
    if not candidate.grounded:
        return None, 'self_reported_ungrounded'

    # Grounding is a citation, not an assertion: a candidate claiming it while citing nothing
    # is precisely the fabrication the gate exists to catch.
    evidence = tuple(item.strip() for item in candidate.evidence if item and item.strip())
    if not evidence:
        return None, 'no_evidence_cited'
    allowed_references = set(packet.reference_ids())
    if any(reference not in allowed_references for reference in evidence):
        return None, 'unknown_evidence_reference'
    if not set(evidence).intersection(packet.grounding_reference_ids()):
        return None, 'no_grounding_reference'

    subject = candidate.subject.strip()
    projection = candidate.projection.strip()
    setting = candidate.setting.strip()
    tone = candidate.tone.strip()
    imperative = candidate.imperative.strip()

    # Setting and tone are required because they own slots in the image graph that nothing
    # else may fill. Without a setting the picture has no place and reverts to the model's
    # idea of the emotion; without a tone its light is decorative rather than this person's.
    if not (subject and projection and setting and tone and imperative):
        return None, 'incomplete'

    # A reproduced exemplar is by definition about someone else's situation, however grounded
    # the model believes it to be.
    if is_exemplar(imperative) or is_exemplar(projection):
        return None, 'copied_exemplar'

    try:
        stage = ProjectionStage(candidate.stage.strip().lower())
    except ValueError:
        return None, 'unknown_stage'

    return (
        SelectedSubject(
            subject=subject,
            stage=stage,
            projection=projection,
            setting=setting,
            tone=tone,
            imperative=imperative,
            evidence=evidence,
        ),
        'admitted',
    )


def _as_candidates(response: Any) -> list[SubjectCandidate]:
    if isinstance(response, RankedSubjects):
        return list(response.candidates)
    return list(RankedSubjects.model_validate(response).candidates)


def build_selection_prompt(
    packet: EvidencePacket,
    *,
    previous: Sequence[Mapping[str, Any]] = (),
) -> str:
    stages = '\n'.join(f'  {stage.value} — {name}' for stage, name in STAGE_NAMES.items())

    sections = [
        'You are producing a projection for one person, from their own recent material.',
        (
            'A projection is not a summary of the week and not advice. It is an image of a '
            'future state — what it looks like on the other side of the thing they keep '
            'circling — carrying one line of text.'
        ),
        (
            'RANK BY EMOTIONAL CHARGE.\n'
            'Rank their open threads by how much charge each carries: what keeps returning '
            'across days, what is circled and left unresolved, what is avoided. Recurrence is '
            'the strongest evidence of charge — read it in the prose; there is no counter to '
            'consult. Do NOT filter by whether an action is available, and do not prefer '
            'tidy threads over heavy ones. Rank by charge alone.'
        ),
        (
            f'Return up to {MAX_CANDIDATES} candidates in rank order, highest charge first. '
            'For each one:\n'
            '  subject     — a short neutral label for the thread\n'
            '  stage       — exactly one key from the list below\n'
            '  projection  — the imagery of the future state, present tense, concrete and '
            'specific to this person\'s actual situation. This is what gets rendered, so it '
            'must describe a scene rather than name a feeling: who or what is there, and what '
            'is happening.\n'
            '  setting     — the real place this happens in and the actual objects in it. '
            'If they named a city, a street, a building or a room, name it here explicitly; a '
            'generic version of the place is a failure, because this field is the only thing '
            'that tells the painter where it is. Add the hour and the specific objects they '
            'mentioned. A viewer who knows their situation must recognise it, and no symbol '
            'may stand in for the place.\n'
            '  tone        — the emotional charge this carries for them, in plain words and '
            'grounded in how they actually spoke about it: apprehensive, elated, resigned, '
            'exposed, and so on, with the shade of it that matters. Do not name colours; the '
            'light is derived from this.\n'
            '  imperative  — the line that ships beside the image\n'
            '  evidence    — one or more exact reference IDs from the material below, such '
            'as conversation:abc or action_item:def. Return only those IDs, without brackets '
            'or commentary. At least one conversation or action-item ID is required; '
            'goal:active can add context but cannot ground a candidate by itself.\n'
            '  grounded    — true only if the imperative follows from the evidence you cited. '
            'If you had to supply the substance yourself, it is false. Say so; a later '
            'candidate will be used, and that is the correct outcome.'
        ),
        f'STAGES:\n{stages}',
        f'REGISTER — the voice, in the product author\'s own words:\n{REGISTER}',
        (
            'VOICE SAMPLES — finished lines from readings already delivered to OTHER PEOPLE, '
            'about their situations, not this one. Study the cadence, the length, the way an '
            'observation and a call to action sit together.\n\n'
            + exemplars_as_prompt_text()
            + '\n\nEvery line above is spent. Reusing one, in whole or in part, is a failed '
            'response — it would deliver another person\'s reading to this person. Write new '
            'lines about the material below.'
        ),
    ]

    if previous:
        shown = '\n'.join(
            f'- {str(item.get("subject") or "").strip()}: {str(item.get("imperative") or "").strip()}'
            for item in list(previous)[:MAX_PREVIOUS]
        )
        sections.append(
            'ALREADY SHOWN TO THEM, most recent first. You are one continuing voice, not a '
            'series of unrelated readings. If a thread here has not moved, that persistence '
            'is itself charge; if it has, do not repeat it.\n' + shown
        )

    sections.append(f'THEIR MATERIAL, from the last {packet.window_days} days:\n{packet.as_prompt_text()}')

    return '\n\n'.join(sections)
