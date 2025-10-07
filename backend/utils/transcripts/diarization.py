import json
import logging
from typing import List, Set

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.transcript_segment import TranscriptSegment
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)


class MergeInstruction(BaseModel):
    segment_id: str = Field(..., description='Segment that should reuse an earlier speaker label')
    adopt_segment_id: str = Field(..., description='Earlier segment whose speaker label should be copied')


class MergeResponse(BaseModel):
    merges: List[MergeInstruction] = Field(default_factory=list)


_parser = PydanticOutputParser(pydantic_object=MergeResponse)
_prompt = ChatPromptTemplate.from_messages(
    [
        (
            'system',
            (
                'You are assisting with light speaker-diarization cleanup on a noisy transcript. '
                'You will receive a chronological list of segments with current speaker labels. '
                'Your task is ONLY to flag cases where a non-user segment was mislabeled and should adopt an earlier speaker label. '
                'Rules:\n'
                '- Never modify segments marked as coming from the user.\n'
                '- Only reassign a segment to an earlier speaker when you are nearly certain they are the same person. If there is any doubt, do nothing.\n'
                '- Do not invent new speakers; rely on the existing ids.\n'
                '- When unsure, do nothing.\n'
                '- Keep the conversation order untouched.\n'
                'Respond strictly with the JSON schema below.\n'
                '{format_instructions}'
            ),
        ),
        (
            'human',
            (
                'Here are the segments (in order):\n'
                '{segments_json}\n\n'
                'List only the segments that should copy the speaker label from an earlier segment. '
                'If no fixes are required, return an empty list.'
            ),
        ),
    ]
).partial(format_instructions=_parser.get_format_instructions())
_chain = _prompt | llm_mini | _parser


async def suggest_speaker_merges(segments: List[TranscriptSegment]) -> List[MergeInstruction]:
    if len(segments) < 4:
        return []

    payload = [
        {
            'id': segment.id,
            'speaker': segment.speaker or f'SPEAKER_{segment.speaker_id:02d}',
            'speaker_id': segment.speaker_id,
            'is_user': segment.is_user,
            'text': segment.display_text(),
        }
        for segment in segments
    ]
    segments_json = json.dumps(payload, ensure_ascii=False)

    try:
        response: MergeResponse = await _chain.ainvoke({'segments_json': segments_json})
        return response.merges
    except Exception as exc:  # noqa: BLE001
        logger.warning('Speaker merge suggestion failed: %s', exc)
        return []


def apply_speaker_merges(conversation_segments: List[TranscriptSegment], instructions: List[MergeInstruction]) -> Set[int]:
    if not instructions:
        return set()

    id_to_index = {segment.id: idx for idx, segment in enumerate(conversation_segments)}
    changed_indices: Set[int] = set()

    for instruction in instructions:
        seg_idx = id_to_index.get(instruction.segment_id)
        target_idx = id_to_index.get(instruction.adopt_segment_id)
        if seg_idx is None or target_idx is None:
            continue
        if seg_idx <= target_idx:
            continue

        segment = conversation_segments[seg_idx]
        target = conversation_segments[target_idx]

        if segment.is_user or target.is_user:
            continue

        segment.speaker = target.speaker
        segment.speaker_id = target.speaker_id
        segment.person_id = target.person_id
        changed_indices.add(seg_idx)

    return changed_indices