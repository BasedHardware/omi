"""Untrusted client-authored conversation projection (free-tier local models).

A projection is display. It is NEVER written to Pinecone vectors, memories/facts,
goals, tasks/action-item stores that feed intelligence, app-selection prompts,
chat RAG cards, or memory-sweep inputs. There is no promotion step.

The one permitted consumer is display (and the opt-in daily recap, which may
render projections). Canonical ``structured`` stays server-authored.

Wire values are not repaired: booleans and integers are strict JSON primitives,
and datetimes must be timezone-aware ISO-8601 strings (not unix timestamps).
String caps apply to the RAW wire value: a padded-past-cap string is rejected,
not stripped into range. Surrounding whitespace on an already-in-cap string is
stripped (incidental, not a walk-past). A ValidationError here is a rejected
projection, not a rejected conversation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
)

from models.conversation_enums import CategoryEnum

CLIENT_PROCESSING_SCHEMA_VERSION = 1

# Every Conversation field that is a client-authored display projection.
#
# This is load-bearing, not documentation: each sink that must not leak a
# projection consults this set rather than naming a field, so classifying a new
# sibling here strips it at every sink at once. A trust-boundary test generates
# a case per (field, sink) from this set, and pins Conversation's field list so
# an unclassified new field cannot be added silently. Lives here because it is
# the projection's own schema module and imports nothing heavy -- database/
# must not import utils/, and the persist helpers stay coordinator-free.
PROJECTION_FAMILY_FIELDS: frozenset[str] = frozenset({'client_processing'})


def _bound_raw_then_strip(*, max_length: int, min_length: int = 0) -> BeforeValidator:
    """Bound the RAW wire string, then strip. Do not trim over-cap values into range.

    Pydantic's ``strip_whitespace`` runs before ``max_length``, so a
    ``StringConstraints`` cap alone accepts ``' ' * 10**6 + 'x'`` and silently
    repairs it to ``'x'``. A BeforeValidator that only checks raw length then
    defers strip to StringConstraints lets whitespace-only values pass
    ``min_length`` on the unstripped form and land as ``''``. This validator
    owns both steps: refuse raw over the cap, strip, then refuse empty-after-strip
    when ``min_length`` requires a value.
    """

    def _check(value: object) -> object:
        if not isinstance(value, str):
            return value
        if len(value) > max_length:
            raise ValueError(f'string too long ({len(value)} > {max_length})')
        stripped = value.strip()
        if len(stripped) < min_length:
            raise ValueError(f'string too short ({len(stripped)} < {min_length})')
        return stripped

    return BeforeValidator(_check)


# Caps bind the RAW wire string. In-cap surrounding whitespace is then stripped.
_Heading = Annotated[
    str,
    _bound_raw_then_strip(max_length=120, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
_SectionBody = Annotated[
    str,
    _bound_raw_then_strip(max_length=4000, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]
_Overview = Annotated[
    str,
    _bound_raw_then_strip(max_length=4000),
    StringConstraints(strip_whitespace=True, max_length=4000),
]
_Emoji = Annotated[
    str,
    _bound_raw_then_strip(max_length=8),
    StringConstraints(strip_whitespace=True, max_length=8),
]
_ActionDescription = Annotated[
    str,
    _bound_raw_then_strip(max_length=500, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
_EventTitle = Annotated[
    str,
    _bound_raw_then_strip(max_length=200, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
_EventDescription = Annotated[
    str,
    _bound_raw_then_strip(max_length=1000),
    StringConstraints(strip_whitespace=True, max_length=1000),
]
_ProvenanceId = Annotated[
    str,
    _bound_raw_then_strip(max_length=120, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
_Runtime = Annotated[
    str,
    _bound_raw_then_strip(max_length=60, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
]
_DeviceClass = Annotated[
    str,
    _bound_raw_then_strip(max_length=60, min_length=1),
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
]
_TranscriptSha256 = Annotated[str, StringConstraints(min_length=64, max_length=64, pattern=r'^[a-f0-9]{64}$')]


def _reject_numeric_datetime(value: object) -> object:
    """Refuse unix timestamps so ``0`` cannot become 1970-01-01.

    Strings and datetime objects pass through; ``AwareDatetime`` then requires
    timezone info, rejecting naive ISO-8601 values.
    """
    if isinstance(value, (int, float)):
        raise ValueError('expected a timezone-aware ISO-8601 datetime string, not a number')
    return value


_AwareIsoDatetime = Annotated[AwareDatetime, BeforeValidator(_reject_numeric_datetime)]


def _reject_coerced_schema_version(value: object) -> object:
    """Refuse bools and floats so JSON ``true`` / ``1.0`` cannot become ``1``.

    Python's ``bool`` is an ``int`` subclass and pydantic's ``Literal[1]`` is
    lax: ``True == 1`` and ``1.0`` coerce to ``1``. This field names the
    contract the client is speaking; silent repair is rejected everywhere
    else on this schema. ``Strict()`` cannot wrap a literal, so this
    BeforeValidator is the gate.
    """
    if isinstance(value, (bool, float)):
        raise ValueError('schema_version must be the JSON integer 1, not a boolean or float')
    return value


_SchemaVersion = Annotated[Literal[1], BeforeValidator(_reject_coerced_schema_version)]


class ProjectedActionItem(BaseModel):
    """Display-only action item. No ids, owners, due dates, or capture fields."""

    model_config = ConfigDict(extra='forbid')

    description: _ActionDescription
    completed: StrictBool = False


class ProjectedSection(BaseModel):
    model_config = ConfigDict(extra='forbid')

    heading: _Heading
    body_markdown: _SectionBody


class ProjectedEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: _EventTitle
    description: _EventDescription = ''
    start: _AwareIsoDatetime
    duration: StrictInt = Field(ge=1, le=1440)


class ProjectedStructure(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: _Heading
    overview: _Overview = ''
    emoji: _Emoji = '🧠'
    category: CategoryEnum = CategoryEnum.other
    sections: list[ProjectedSection] = Field(default_factory=list[ProjectedSection], max_length=12)
    events: list[ProjectedEvent] = Field(default_factory=list[ProjectedEvent], max_length=12)


class ProjectionProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model_id: _ProvenanceId
    runtime: _Runtime
    device_class: _DeviceClass
    generated_at: _AwareIsoDatetime


class ClientProcessing(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: _SchemaVersion
    transcript_sha256: _TranscriptSha256
    structure: ProjectedStructure
    action_items: list[ProjectedActionItem] = Field(default_factory=list[ProjectedActionItem], max_length=25)
    provenance: ProjectionProvenance
