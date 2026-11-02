"""Turn-local evidence gate for explicit transcript recall; contains no speech."""

from dataclasses import dataclass
from typing import Any

UNVERIFIED_TRANSCRIPT_ANSWER = (
    "I couldn't verify that from the saved transcripts searched so far. "
    "I won't guess; a narrower date or another phrase can help continue the search."
)
_STATE_KEY = '_transcript_recall_evidence'

TRANSCRIPT_RECALL_INSTRUCTIONS = """
<transcript_recall>
When the user asks to search transcripts or verify a spoken detail, call search_conversations_tool
with transcript_query containing a short literal phrase or distinctive words (for example "invoice").
This reads saved transcripts directly, including unindexed history. Follow its transcript_cursor
with the same query and dates when a page is incomplete. If the tool budget ends first, say the
search is incomplete; never describe a title/summary miss as a full transcript search.
Base precise personal facts (amounts, dates, names) on the returned verbatim evidence and cite its
conversation. A previous assistant answer, user pushback or a plausible near match is not evidence.
If evidence is still missing after a retry, say what you could not verify rather than invent a detail.
</transcript_recall>"""


@dataclass
class TranscriptRecallEvidence:
    found: bool = False


def begin_transcript_recall(configurable: dict[str, Any]) -> TranscriptRecallEvidence:
    state = configurable.setdefault(_STATE_KEY, TranscriptRecallEvidence())
    if not isinstance(state, TranscriptRecallEvidence):
        state = TranscriptRecallEvidence()
        configurable[_STATE_KEY] = state
    return state


def transcript_recall_unverified(configurable: dict[str, Any]) -> bool:
    state = configurable.get(_STATE_KEY)
    return isinstance(state, TranscriptRecallEvidence) and not state.found
