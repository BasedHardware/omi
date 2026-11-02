"""Shared reversible edit contract, additive to the released Review edit arm."""

from pydantic import Field, model_validator
from typing import ClassVar
from models.dream_edit import Edit, MemoryHygieneEdit, Strict, QUESTION_VALUE_DESCRIPTION
from utils.agent_capabilities.registry import EDIT_KINDS, ALL_EDIT_KINDS


class HarnessEdit(Strict):
    _dream_authority: ClassVar[bool] = False
    kind: str = Field(
        json_schema_extra={'enum': list(EDIT_KINDS)},
        description=(
            'Correct evidenced defects, never style or low importance. Retire memories only for garbage, '
            'contradiction or facts spoken by someone else but attributed to the owner. Supersede only with '
            'a newer fact about the same attribute. Dismiss junk person detections (filler, nationalities, '
            'fragments), never a real person. Merge tasks only when they represent the same obligation; '
            'retire duplicates or someone else\'s task misfiled to the owner. Autonomous agents must not change manual or edited '
            'tasks. Merge conversations only for overlapping captures of the same speech, preserving both '
            'records and audio. Set language to the language actually spoken, never translate speech.'
        ),
    )
    target: str = Field(min_length=3, max_length=256, description=Edit.model_fields['target'].description)
    other: str = Field(
        default='',
        max_length=256,
        description=(
            'Second fully read ref for a merge; target is retired into other for task/conversation merges. '
            'For supersede_memory, the existing newer memory. Otherwise empty.'
        ),
    )
    before: str = Field(default='', max_length=16000, description=Edit.model_fields['before'].description)
    after: str = Field(
        default='',
        max_length=16000,
        description=(
            'Corrected text or new language tag. For supersede_memory choose new fact text OR other. '
            'Empty for retirement, dismissal and task/conversation/person merges: preserve the survivor.'
        ),
    )
    effective_from: str = Field(
        default='', max_length=40, description=MemoryHygieneEdit.model_fields['effective_from'].description
    )
    reason: str = Field(min_length=1, max_length=1000, description='Explain the defect and cited evidence.')
    evidence: list[str] = Field(
        min_length=1,
        max_length=10,
        description=(
            'Fully read owner refs, with segment ids for speech when available. Cited evidence must '
            'support this change; do not invent refs or use the old memory itself as retirement support.'
        ),
    )
    value: int = Field(default=3, ge=1, le=5, description=QUESTION_VALUE_DESCRIPTION)
    why_it_matters: str = Field(default='', max_length=200, description='Short explanation of future value.')

    @model_validator(mode='after')
    def semantics(self):
        if not self.reason.strip():
            raise ValueError('An edit requires a nonblank reason')
        from utils.agent_capabilities.registry import get_kind

        spec = get_kind(self.kind)
        if spec.dream_only and not self._dream_authority:
            raise ValueError('Dream-private capability is not a released Review edit')
        if not spec.dream_only and len(self.evidence) > 10:
            raise ValueError('Only bounded required-intake inventory may cite more than ten refs')
        if self.effective_from and spec.schema_rule != 'hygiene':
            raise ValueError('Only memory supersession may carry effective_from')
        spec.schema(self)
        return self


class DreamHarnessEdit(HarnessEdit):
    """Private planner model; never added to the released Review response arm."""

    _dream_authority: ClassVar[bool] = True
    kind: str = Field(
        json_schema_extra={'enum': list(ALL_EDIT_KINDS)},
        description=(HarnessEdit.model_fields['kind'].description or '')
        + ' resolve_required_memory compares a hidden historical required submission with all supplied canonical evidence; preserve before verbatim and leave after empty.',
    )
    other: str = Field(
        default='',
        max_length=256,
        description=(HarnessEdit.model_fields['other'].description or '')
        + ' For resolve_required_memory, optionally name the existing durable memory covering every material detail.',
    )
    evidence: list[str] = Field(
        min_length=1, max_length=101, description=HarnessEdit.model_fields['evidence'].description
    )
