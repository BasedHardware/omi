import re
from typing import List, Dict

from pydantic import BaseModel, Field

from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from utils.llm.clients import llm_mini, num_tokens_from_string

# Configuration constants
MAX_SEGMENT_TOKENS: int = 6000
PREFERRED_SPAN_SECONDS_MIN: int = 5
PREFERRED_SPAN_SECONDS_MAX: int = 15
MAX_SPAN_SECONDS: int = 20


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p and len(p.strip()) > 0]


def _to_superscript(n: int) -> str:
    mapping = {
        '0': '⁰',
        '1': '¹',
        '2': '²',
        '3': '³',
        '4': '⁴',
        '5': '⁵',
        '6': '⁶',
        '7': '⁷',
        '8': '⁸',
        '9': '⁹',
    }
    s = str(n)
    return ''.join(mapping.get(ch, ch) for ch in s)


class CitationIndex(BaseModel):
    sentenceIndex: int = Field(description="Index in the provided sentences array")
    segmentIndex: int = Field(description="Original index of the transcript segment chosen for this sentence")


class CitationsOutput(BaseModel):
    citations: List[CitationIndex] = Field(default_factory=list)


def _prepare_segments_for_llm(segments: List[TranscriptSegment], max_tokens: int = MAX_SEGMENT_TOKENS) -> List[Dict]:
    if not segments:
        return []
    items = [
        {
            'index': i,
            'start': float(s.start),
            'end': float(s.end),
            'text': s.text.strip(),
        }
        for i, s in enumerate(segments)
    ]

    joined = "\n".join(it['text'] for it in items)
    tokens = num_tokens_from_string(joined)
    if tokens <= max_tokens:
        return items

    factor = max(2, int(tokens / max_tokens) + 1)
    sampled = [items[i] for i in range(0, len(items), factor)]
    return sampled


def _invoke_citations_llm(sentences: List[str], segments_for_llm: List[Dict]) -> List[CitationIndex]:
    if not sentences or not segments_for_llm:
        return []

    sentences_json = "\n".join([f"{{\"index\": {i}, \"text\": {repr(s)} }}" for i, s in enumerate(sentences)])
    segments_json = "\n".join(
        [
            f"{{\"index\": {it['index']}, \"start\": {it['start']}, \"end\": {it['end']}, \"text\": {repr(it['text'])} }}"
            for it in segments_for_llm
        ]
    )

    prompt = f"""
You are given two arrays:

<sentences>
{sentences_json}
</sentences>

<segments>
{segments_json}
</segments>

Task: For each <sentences> item, pick at most ONE segment from <segments> that best supports the sentence.

Hard constraints:
- Output at most one segment per sentence.
- Prefer short, high-signal spans (ideally {PREFERRED_SPAN_SECONDS_MIN}–{PREFERRED_SPAN_SECONDS_MAX} seconds; never exceed {MAX_SPAN_SECONDS} seconds).
- IMPORTANT: Use the segment 'index' field (original indices) when you output.
- If no segment is clearly relevant, omit that sentence entirely.

Output ONLY the JSON object in the exact schema below:
{{
  "citations": [
    {{ "sentenceIndex": number, "segmentIndex": number }},
    ...
  ]
}}
""".strip()

    try:
        output: CitationsOutput = llm_mini.with_structured_output(CitationsOutput).invoke(prompt)
        return output.citations or []
    except Exception as e:
        print('[CITATIONS LLM] error:', e)
        return []


def compute_overview_citations(conversation: Conversation) -> List[Dict]:
    """Compute citations for structured.overview.

    Returns a list of objects: { sentenceIndex, startTime, endTime }.
    No markdown is produced here; markdown is rendered on-demand by
    render_overview_citations_markdown.
    """
    overview = conversation.structured.overview or ""
    sentences = _split_sentences(overview)
    segments = conversation.transcript_segments or []

    if not overview or not segments:
        return []

    segments_for_llm = _prepare_segments_for_llm(segments)

    plans = _invoke_citations_llm(sentences, segments_for_llm)

    citations: List[Dict] = []

    for idx, _ in enumerate(sentences):
        plan = next((p for p in plans if p.sentenceIndex == idx), None)
        if plan is None:
            continue
        if plan.segmentIndex < 0 or plan.segmentIndex >= len(segments):
            continue
        seg = segments[plan.segmentIndex]
        citations.append(
            {
                'sentenceIndex': idx,
                'startTime': float(seg.start),
                'endTime': float(seg.end),
            }
        )

    return citations


def render_overview_citations_markdown(overview: str, citations: List[Dict]) -> str:
    """Render overview text with footnote-style omi:// links using citations.

    Input: plain overview string and the citations array from compute_overview_citations.
    Output: markdown string with superscript markers linking to the transcript ranges.
    """
    sentences = _split_sentences(overview or "")
    if not sentences:
        return overview or ""

    annotated_parts: List[str] = []
    for idx, sent in enumerate(sentences):
        cite = next((c for c in citations if c.get('sentenceIndex') == idx), None)
        if not cite:
            annotated_parts.append(sent)
            continue
        start_time = float(cite.get('startTime', 0))
        end_time = float(cite.get('endTime', 0))
        link = f"omi://time?start={start_time:.2f}&end={end_time:.2f}"
        marker = _to_superscript(idx + 1)
        annotated_parts.append(f"{sent} [{marker}]({link})")

    return " ".join(annotated_parts).strip()
