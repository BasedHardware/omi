"""Live-model adapter for the separately versioned What Matters Now judgment."""

import json
from typing import Any, Callable, cast

from pydantic import BaseModel, ConfigDict, Field

from utils.llm.model_config import get_model_config
from utils.task_intelligence.recommendations import (
    MAX_RECOMMENDATIONS,
    EvaluationSubject,
    JudgmentSelection,
)


class JudgmentOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    selections: list[JudgmentSelection] = Field(max_length=MAX_RECOMMENDATIONS)


class LiveRecommendationJudgment:
    """One structured call over a deterministically filtered shortlist."""

    def __init__(self, llm_provider: Callable[[], Any]) -> None:
        model, provider = get_model_config('what_matters_now')
        self.model_version = f'{provider}:{model}'
        self._llm_provider = llm_provider

    def judge(self, subjects: list[EvaluationSubject]) -> list[JudgmentSelection]:
        if not subjects:
            return []
        subject_payload = [
            {
                'subject_id': subject.subject_id,
                'subject_kind': subject.kind.value,
                'headline': subject.headline,
                'goal_or_workstream_label': subject.label,
                'evidence_preview': subject.evidence_preview,
                'facts': subject.facts.model_dump(mode='json'),
            }
            for subject in subjects
        ]
        prompt = (
            'Select zero to three genuinely useful items for the user to act on now. '
            'Judge the set holistically; do not calculate or return component scores. '
            'Use only supplied subject_kind + subject_id pairs. Empty is valid. Return a concrete action and a concise why-now.\n'
            + json.dumps(subject_payload, separators=(',', ':'), ensure_ascii=False)
        )
        parser = self._llm_provider().with_structured_output(JudgmentOutput)
        output = cast(JudgmentOutput, parser.invoke(prompt))
        return output.selections


__all__ = ['LiveRecommendationJudgment']
