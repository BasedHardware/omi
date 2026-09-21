"""Only an explicit self-introduction may create a Person from transcript text.

The live listen path ran every unattributed segment through the name patterns and
created a Person for any hit. The English pattern accepts any capitalized token
after "I'm", and Chinese 我是 ("I am") is ordinary speech, so a real account
accumulated dozens of people named after nationalities, brands, sentence-cased
fillers and clause fragments — all of them permanent entries in the speaker
picker. Matching stays loose (a hit still resolves a person the user already
has); creation is now gated on the phrasing that actually carries the authority.
"""

import asyncio
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from models.transcript_segment import TranscriptSegment  # noqa: E402
from routers.listen import transcripts  # noqa: E402


class _Recorder:
    """Stands in for the listen host's persistence executor.

    Records every call so a test can assert on what reached the database, and
    answers ``get_person_by_name`` from a fixed table of people the user has.
    """

    def __init__(self, existing_people=None):
        self.existing = existing_people or {}
        self.created = []
        self.lookups = []

    async def call(self, fn, *args, **kwargs):
        name = getattr(fn, '__name__', '')
        if name == 'get_person_by_name':
            self.lookups.append(args[1])
            return self.existing.get(args[1])
        if name == 'create_person':
            self.created.append(args[1])
            return args[1]
        return None


def _processor(recorder, *, owner_name=None, create_speakers=True, language=None):
    async def resolve_owner_name():
        return owner_name

    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.suggested_segments = set()
    processor.host = SimpleNamespace(
        language=language,
        state=SimpleNamespace(
            speaker_id_enabled=False,
            current_conversation_id='c1',
            first_audio_byte_timestamp=0.0,
            speaker_map_dirty=False,
        ),
        speakers=SimpleNamespace(
            speaker_to_person={},
            person_embeddings={},
            segment_assignments={},
            queue=asyncio.Queue(),
            resolve_owner_name=resolve_owner_name,
        ),
        persistence=recorder,
        request=SimpleNamespace(uid='u1', create_speakers=create_speakers, speaker_auto_assign_enabled=False),
        send_event=lambda event: None,
    )
    return processor


def _segment(text):
    return TranscriptSegment(id='s1', text=text, speaker_id=1, is_user=False, start=0.0, end=4.0)


def _run(processor, text):
    asyncio.run(processor._speaker_detection([_segment(text)], 0.0))


@pytest.mark.parametrize(
    "text",
    [
        "I'm Chinese.",
        "I am American.",
        "I'm Googling it now.",
        "I'm Amazon shopping.",
        "I'm Always late.",
    ],
)
def test_bare_copula_never_creates_a_person(text):
    recorder = _Recorder()
    _run(_processor(recorder), text)
    assert recorder.created == [], f"{text!r} minted a person: {recorder.created}"


@pytest.mark.parametrize("text", ["我是因为这个", "我是一碗稀饭，"])
def test_chinese_copula_never_creates_a_person(text):
    recorder = _Recorder()
    _run(_processor(recorder, language='zh'), text)
    assert recorder.created == []


def test_explicit_introduction_still_creates_a_person():
    recorder = _Recorder()
    _run(_processor(recorder), "My name is Alice and I build bicycles.")
    assert [p['name'] for p in recorder.created] == ["Alice"]


def test_copula_still_resolves_a_person_the_user_already_has():
    """A loose hit is good enough to reuse an existing person — just not to create one."""
    recorder = _Recorder(existing_people={'Robin': {'id': 'person-robin', 'name': 'Robin'}})
    processor = _processor(recorder)
    _run(processor, "I'm Robin, good to meet you.")

    assert recorder.created == []
    assert recorder.lookups == ['Robin']
    assert processor.host.speakers.segment_assignments == {'s1': 'person-robin'}


def test_owner_name_is_never_minted_as_a_separate_person():
    """Hearing the owner's own name produced a "David" beside "David (You)"."""
    recorder = _Recorder()
    processor = _processor(recorder, owner_name='David')
    _run(processor, "My name is David and I spend most of my time vibe coding.")

    assert recorder.created == []
    assert recorder.lookups == [], 'the owner is identified by voice, so do not even look them up'
    assert processor.host.speakers.segment_assignments == {}


def test_owner_name_match_is_case_insensitive():
    recorder = _Recorder()
    _run(_processor(recorder, owner_name='david'), "My name is David.")
    assert recorder.created == []


def test_create_speakers_disabled_still_suppresses_creation():
    recorder = _Recorder()
    _run(_processor(recorder, create_speakers=False), "My name is Alice.")
    assert recorder.created == []
