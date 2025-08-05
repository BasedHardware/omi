# We want these types to be flexible to allow for updated API responses
# or cutting-edge options to not break the client for older SDK versions;
# as such, everything is implemented using TypedDicts
# instead of, say, dataclasses.

import sys
from datetime import datetime
from typing import Optional, List, Union, Any, Dict

if sys.version_info >= (3, 8):
    from typing import TypedDict, Literal
else:
    from typing_extensions import TypedDict, Literal
if sys.version_info >= (3, 9, 2):
    from collections.abc import Callable, Awaitable
else:
    from typing import Callable, Awaitable


class UpdateResponse(TypedDict):
    message: str


# Transcription


class Options(TypedDict, total=False):
    api_key: str
    api_url: str  # this URL should /not/ include a trailing slash
    suppress_warnings: bool
    raise_warnings_as_errors: bool


class UrlSource(TypedDict):
    url: str


class BufferSource(TypedDict):
    buffer: bytes
    mimetype: str


TranscriptionSource = Union[UrlSource, BufferSource]


BoostedKeyword = TypedDict(
    "BoostedKeyword",
    {
        "word": str,
        "boost": float,
    },
)
Keyword = Union[str, BoostedKeyword]


class TranscriptionOptions(TypedDict, total=False):
    # References for the different meanings and values of these properties
    # can be found in the Deepgram docs:
    # https://developers.deepgram.com/documentation/features/
    model: str
    version: str
    language: str
    punctuate: bool
    profanity_filter: bool
    redact: List[str]
    diarize: Literal["false", "true"]
    diarize_version: str
    version: str
    multichannel: bool
    alternatives: int
    # numerals will be deprecated in the future
    numerals: bool
    numbers: bool
    numbers_spaces: bool
    search: List[str]
    callback: str
    keywords: List[str]
    keyword_boost: str
    ner: str
    tier: str
    dates: bool
    date_format: str
    times: bool
    dictation: bool
    measurements: bool
    smart_format: bool
    replace: Union[str, List[str]]
    tag: List[str]
    filler_words: bool


class PrerecordedOptions(TranscriptionOptions, total=False):
    # References for the different meanings and values of these properties
    # can be found in the Deepgram docs:
    # https://developers.deepgram.com/documentation/features/
    utterances: bool
    utt_split: float
    detect_entities: bool
    summarize: Union[bool, str]
    paragraphs: bool
    detect_language: bool
    detect_topics: bool
    translate: List[str]
    analyze_sentiment: bool
    sentiment: bool
    sentiment_threshold: float


class LiveOptions(TranscriptionOptions, total=False):
    # References for the different meanings and values of these properties
    # can be found in the Deepgram docs:
    # https://developers.deepgram.com/documentation/features/
    interim_results: bool
    endpointing: bool
    vad_turnoff: int
    encoding: str
    channels: int
    sample_rate: int


class ToggleConfigOptions(TypedDict):
    numerals: bool


class WordBase(TypedDict):
    word: str
    start: float
    end: float
    confidence: float
    speaker: Optional[int]
    speaker_confidence: Optional[float]
    punctuated_word: Optional[str]


class Hit(TypedDict):
    confidence: float
    start: float
    end: float
    snippet: str


class Search(TypedDict):
    query: str
    hits: List[Hit]


class Translation(TypedDict):
    translation: str
    language: str


class Alternative(TypedDict):
    transcript: str
    confidence: float
    words: List[WordBase]
    detected_language: Optional[str]
    translation: Optional[List[Translation]]


class Summary(TypedDict):
    summary: str
    start_word: float
    end_word: float


class Entity(TypedDict):
    label: str
    value: str
    confidence: float
    start_word: float
    end_word: float


class Sentence(TypedDict):
    text: str
    start: float
    end: float


class Paragraph(TypedDict):
    sentences: List[Sentence]
    num_words: float
    start: float
    end: float


class ParagraphGroup(TypedDict):
    transcript: str
    paragraphs: List[Paragraph]


class Topic(TypedDict):
    topics: List[str]
    text: str
    start_word: float
    end_word: float


class Channel(TypedDict):
    search: Optional[List[Search]]
    alternatives: List[Alternative]
    summaries: Optional[List[Summary]]
    entities: Optional[List[Entity]]
    paragraphs: Optional[ParagraphGroup]
    topics: Optional[List[Topic]]


class Utterance(TypedDict):
    start: float
    end: float
    confidence: float
    channel: int
    transcript: str
    words: List[WordBase]
    speaker: Optional[int]
    speaker_confidence: Optional[float]
    id: str


class Warning(TypedDict):
    parameter: str
    type: Literal[
        "unsupported_language",
        "unsupported_model",
        "unsupported_encoding",
        "deprecated",
    ]
    message: str


class SummaryV2(TypedDict):
    short: str
    result: Literal["success", "failure"]


class Metadata(TypedDict):
    request_id: str
    transaction_key: str
    sha256: str
    created: str
    duration: float
    channels: int
    models: List[str]
    model_info: Dict[str, Any]
    warnings: List[Warning]


TranscriptionResults = TypedDict(
    "TranscriptionResults",
    {
        "channels": List[Channel],
        "utterances": Optional[List[Utterance]],
        "summary": Optional[SummaryV2],
    },
)


class PrerecordedTranscriptionResponse(TypedDict, total=False):
    request_id: str
    metadata: Metadata
    results: TranscriptionResults


StreamingMetadata = TypedDict(
    "StreamingMetadata",
    {
        "request_id": str,
        "model_uuid": str,
    },
)


class LiveTranscriptionResponse(TypedDict):
    channel_index: List[int]
    duration: float
    start: float
    is_final: bool
    speech_final: bool
    channel: Channel
    metadata: StreamingMetadata


EventHandler = Union[Callable[[Any], None], Callable[[Any], Awaitable[None]]]


# Keys


class Key(TypedDict):
    api_key_id: str
    key: Optional[str]
    comment: str
    created: datetime
    scopes: List[str]


# Members


class Member(TypedDict):
    email: str
    first_name: str
    last_name: str
    id: str
    scopes: Optional[List[str]]


class KeyBundle(TypedDict):
    api_key: Key
    member: Member


class KeyResponse(TypedDict):
    api_keys: List[KeyBundle]


# Projects


class Project(TypedDict):
    project_id: str
    name: str


class ProjectResponse(TypedDict):
    projects: List[Project]


# Usage


class UsageRequestListOptions(TypedDict):
    start: Optional[str]
    end: Optional[str]
    page: Optional[int]
    limit: Optional[int]
    status: Literal["succeeded", "failed"]


class UsageRequestDetails(TypedDict):
    usd: float
    dutation: float
    total_audio: float
    channels: int
    streams: int
    model: str
    method: Literal["sync", "async", "streaming"]
    tags: List[str]
    features: List[str]
    config: Dict[str, bool]  # TODO: add all possible request options


class UsageRequestDetail(TypedDict):
    details: UsageRequestDetails


class UsageRequestMessage(TypedDict):
    message: Optional[str]


class UsageCallback(TypedDict):
    code: int
    completed: str


class UsageRequest(TypedDict):
    request_id: str
    created: str
    path: str
    accessor: str
    response: Optional[Union[UsageRequestDetail, UsageRequestMessage]]
    callback: Optional[UsageCallback]


class UsageRequestList(TypedDict):
    page: int
    limit: int
    requests: Optional[List[UsageRequest]]


class UsageOptions(TypedDict, total=False):
    start: str
    end: str
    accessor: str
    tag: List[str]
    method: Literal["sync", "async", "streaming"]
    model: str
    multichannel: bool
    interim_results: bool
    punctuate: bool
    ner: bool
    utterances: bool
    replace: Union[str, List[str]]
    profanity_filter: bool
    keywords: bool
    diarize: bool
    detect_language: bool
    search: bool
    redact: bool
    alternatives: bool
    numerals: bool
    detect_entities: bool
    summarize: Union[bool, str]
    paragraphs: bool
    detect_language: bool
    detect_topics: bool
    translate: bool
    analyze_sentiment: bool
    sentiment_threshold: float


class UsageResponseDetail(TypedDict):
    start: str
    end: str
    hours: float
    requests: int


UsageResponseResolution = TypedDict(
    "UsageResponseResolution", {"units": str, "amount": int}
)


class UsageResponse(TypedDict):
    start: str
    end: str
    resolution: UsageResponseResolution
    results: List[UsageResponseDetail]


class UsageFieldOptions(TypedDict, total=False):
    start: str
    end: str


class UsageField(TypedDict):
    tags: List[str]
    models: List[str]
    processing_methods: List[str]
    languages: List[str]
    features: List[str]


# Billing


class Balance(TypedDict):
    balance_id: str
    amount: float
    units: str
    purchase: str


class BalanceResponse(TypedDict):
    projects: List[Balance]


# Scope


class Scope(TypedDict):
    scopes: List[str]


# Invitation


class Invitation(TypedDict):
    email: str
    scope: str


class InvitationResponse(TypedDict):
    message: str
