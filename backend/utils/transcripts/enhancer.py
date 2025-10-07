import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.transcript_segment import TranscriptSegment
from utils.llm.clients import llm_nano

logger = logging.getLogger(__name__)

_MIN_CHAR_THRESHOLD = int(os.getenv('TRANSCRIPT_ENHANCER_MIN_CHARS', '220'))
_MIN_SEGMENT_THRESHOLD = int(os.getenv('TRANSCRIPT_ENHANCER_MIN_SEGMENTS', '4'))
_MAX_CHAR_THRESHOLD = int(os.getenv('TRANSCRIPT_ENHANCER_MAX_CHARS', '1200'))

_buffers: Dict[str, List[Dict[str, str]]] = {}
_locks: Dict[str, asyncio.Lock] = {}


@dataclass
class MergeInstruction:
    segment_id: str
    adopt_segment_id: str


@dataclass
class EnhancementResult:
    enhancements: Dict[str, str]
    merges: List[MergeInstruction]


class EnhancedSegmentModel(BaseModel):
    id: str = Field(..., description='The segment identifier to rewrite')
    text: str = Field(..., description='Enhanced transcript text for this segment')


class MergeInstructionModel(BaseModel):
    segment_id: str = Field(..., description='Segment that should reuse an earlier speaker label')
    adopt_segment_id: str = Field(..., description='Earlier segment whose speaker label should be copied')


class EnhancedSegmentsResponse(BaseModel):
    segments: List[EnhancedSegmentModel] = Field(default_factory=list)
    merges: List[MergeInstructionModel] = Field(default_factory=list)


_parser = PydanticOutputParser(pydantic_object=EnhancedSegmentsResponse)
_FORMAT_INSTRUCTIONS = _parser.get_format_instructions()
_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            'system',
            (
                'You transform imperfect speech-to-text output into polished, well-punctuated sentences while preserving the facts. '
                'Follow these rules strictly:\n'
                '- Correct grammar, punctuation, casing, and obvious transcription errors.\n'
                '- You may swap words or rephrase sentences only when you are highly confident the new wording reflects the exact same meaning and is more natural. When in doubt, keep the original phrasing.\n'
                '- Maintain the original segment order. Do not merge segments from different speakers.\n'
                '- Merge consecutive segments from the same speaker only when you are absolutely certain they belong together. When you do, repeat the final sentence for every segment id involved so no ids are lost.\n'
                '- Keep the same language as the input; do not translate.\n'
                '- Trim extra whitespace but keep meaningful pauses or ellipses.\n'
                'Return JSON ONLY using this schema:\n{format_instructions}'
            ),
        ),
        (
            'human',
            (
                'Here is the JSON array of transcript segments (speaker,text,id):\n'
                '{segments_json}\n\n'
                'Rewrite each segment to sound natural. '
                'If you merge consecutive segments, repeat the merged sentence for every segment id involved so no ids are lost.\n'
                'If you identify same-speaker segments that should inherit an earlier label, list them explicitly.'
            ),
        ),
    ]
).partial(format_instructions=_FORMAT_INSTRUCTIONS)
_CHAIN = _PROMPT | llm_nano | _parser


def _buffer_key(uid: str, conversation_id: str) -> str:
    return f'{uid}:{conversation_id}'


def _get_lock(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def _segment_payload(segment: TranscriptSegment) -> Dict[str, str]:
    speaker_label = 'User' if segment.is_user else (segment.person_id or f'Speaker {segment.speaker_id}')
    raw_text = (segment.raw_text or segment.text or '').strip()
    return {
        'id': segment.id,
        'speaker': speaker_label,
        'text': raw_text,
    }


def _buffer_stats(buffer: List[Dict[str, str]]) -> Tuple[int, int]:
    char_count = sum(len(item['text']) for item in buffer)
    return len(buffer), char_count


def _should_process(buffer: List[Dict[str, str]]) -> bool:
    if not buffer:
        return False
    segment_count, char_count = _buffer_stats(buffer)
    return segment_count >= _MIN_SEGMENT_THRESHOLD or char_count >= _MIN_CHAR_THRESHOLD


def _pop_chunk(buffer: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not buffer:
        return []
    chunk: List[Dict[str, str]] = []
    char_count = 0
    while buffer and (char_count < _MAX_CHAR_THRESHOLD or not chunk):
        item = buffer.pop(0)
        if not item['text']:
            continue
        chunk.append(item)
        char_count += len(item['text'])
        if char_count >= _MAX_CHAR_THRESHOLD and chunk:
            break
    return chunk


async def _enhance_chunk(uid: str, conversation_id: str, chunk: List[Dict[str, str]]) -> EnhancementResult:
    if not chunk:
        return EnhancementResult({}, [])
    segments_json = json.dumps(chunk, ensure_ascii=False)
    try:
        response: EnhancedSegmentsResponse = await _CHAIN.ainvoke({'segments_json': segments_json})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'Transcript enhancement failed for uid=%s conversation=%s: %s',
            uid,
            conversation_id,
            exc,
        )
        raise

    enhancements: Dict[str, str] = {}
    for item in response.segments:
        cleaned = item.text.strip()
        if cleaned:
            enhancements[item.id] = cleaned

    merges = [
        MergeInstruction(segment_id=model.segment_id, adopt_segment_id=model.adopt_segment_id)
        for model in response.merges
    ]

    return EnhancementResult(enhancements, merges)


async def enhance_transcript_segments(
    uid: str,
    conversation_id: str,
    segments: List[TranscriptSegment],
    *,
    force: bool = False,
) -> EnhancementResult:
    """
    Queue new transcript segments for enhancement. Returns both the enhanced text map and any speaker merge suggestions.
    """
    if not segments:
        return EnhancementResult({}, [])

    key = _buffer_key(uid, conversation_id)
    lock = _get_lock(key)
    chunks_to_process: List[List[Dict[str, str]]] = []

    async with lock:
        buffer = _buffers.setdefault(key, [])
        buffer.extend([_segment_payload(segment) for segment in segments if segment.id])
        while buffer and (force or _should_process(buffer)):
            chunk = _pop_chunk(buffer)
            if not chunk:
                break
            chunks_to_process.append(chunk)
            if not force and not _should_process(buffer):
                break
        _buffers[key] = buffer

    combined_enhancements: Dict[str, str] = {}
    combined_merges: List[MergeInstruction] = []

    for chunk in chunks_to_process:
        try:
            chunk_result = await _enhance_chunk(uid, conversation_id, chunk)
        except Exception:
            async with lock:
                _buffers.setdefault(key, [])
                _buffers[key] = chunk + _buffers[key]
            break
        combined_enhancements.update(chunk_result.enhancements)
        combined_merges.extend(chunk_result.merges)

    return EnhancementResult(combined_enhancements, combined_merges)


async def flush_transcript_enhancement(uid: str, conversation_id: str) -> EnhancementResult:
    """
    Force processing of any buffered segments for a conversation.
    """
    key = _buffer_key(uid, conversation_id)
    lock = _locks.get(key)
    if lock is None:
        return EnhancementResult({}, [])

    chunks_to_process: List[List[Dict[str, str]]] = []
    async with lock:
        buffer = _buffers.get(key, [])
        while buffer:
            chunk = _pop_chunk(buffer)
            if not chunk:
                break
            chunks_to_process.append(chunk)
        _buffers[key] = buffer

    combined_enhancements: Dict[str, str] = {}
    combined_merges: List[MergeInstruction] = []

    for chunk in chunks_to_process:
        try:
            chunk_result = await _enhance_chunk(uid, conversation_id, chunk)
        except Exception:
            async with lock:
                _buffers.setdefault(key, [])
                _buffers[key] = chunk + _buffers[key]
            break
        combined_enhancements.update(chunk_result.enhancements)
        combined_merges.extend(chunk_result.merges)

    # Clean up buffers/locks when empty
    async with lock:
        if not _buffers.get(key):
            _buffers.pop(key, None)
            _locks.pop(key, None)

    return EnhancementResult(combined_enhancements, combined_merges)


def apply_speaker_merges(
    conversation_segments: List[TranscriptSegment],
    instructions: List[MergeInstruction],
) -> set:
    """
    Apply speaker merge instructions in-place and return the indices that were updated.
    """
    if not instructions:
        return set()

    id_to_index = {segment.id: idx for idx, segment in enumerate(conversation_segments)}
    changed_indices = set()

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