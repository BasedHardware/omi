"""Approved screen frames as notes evidence: roster names, SCREEN MOMENTS, images.

Pins the three consumption paths and, most importantly, that frame images reach
the provider as image parts through every hop of the notes call (LangChain
payload -> gateway validation -> gateway provider request). A hop that dropped
them would silently turn the call blind; these tests fail instead.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import io  # noqa: E402
import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import google.auth.credentials  # noqa: F401,E402

from models.calendar_context import CalendarMeetingContext, MeetingParticipant  # noqa: E402
from testing.import_isolation import stub_modules  # noqa: E402
from utils.conversations import screen_frame_evidence as evidence_mod  # noqa: E402
from utils.conversations.meeting_context_render import (
    MAX_CONTEXT_PACK_CHARACTERS,
    MeetingContextPack,
    render_meeting_context_pack,
)
from utils.conversations.meeting_participants import normalize_meeting_participants  # noqa: E402
from utils.conversations.screen_frame_evidence import (  # noqa: E402
    ScreenFrameEvidence,
    load_notes_frame_images,
    load_screen_frame_evidence,
    screen_frame_agent_names,
    screen_frame_names,
    screen_moment_lines,
    with_screen_frame_participants,
)
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage, screen_frames_message  # noqa: E402

START = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
_GATEWAY_CONFIG: list = []
_CLIENTS: dict = {}
PROD = 'based-hardware-prod-screen-frames'
DEV = 'based-hardware-dev-screen-frames'


@pytest.fixture(scope='module', autouse=True)
def isolated_imports():
    with stub_modules({}):
        # Keep import and config-load cost out of individual fast-unit timing.
        import langchain_openai  # noqa: F401
        import llm_gateway.gateway.executor  # noqa: F401
        import llm_gateway.gateway.resolver  # noqa: F401
        import utils.llm.conversation_processing  # noqa: F401
        import utils.llm.conversation_prompt_prefix  # noqa: F401
        import utils.llm.gateway_client  # noqa: F401
        from llm_gateway.gateway.config_loader import load_gateway_config

        from langchain_openai import ChatOpenAI
        from utils.llm.gateway_client import GatewayContextChatOpenAI

        _GATEWAY_CONFIG.append(load_gateway_config(prod_mode=True))
        _CLIENTS['direct'] = ChatOpenAI(model='gpt-6-luna', api_key='sk-test')
        _CLIENTS['gateway'] = GatewayContextChatOpenAI(
            model='omi:auto:conv-structure', api_key='svc-test', base_url='http://gateway.invalid/v1'
        )
        _wire_messages_for(_CLIENTS['direct'])  # warm the payload path outside test timing
        yield


def _evidence(frame_id, minutes, names=(), summary='', role='strip'):
    return ScreenFrameEvidence(
        frame_id=frame_id,
        captured_at=START + timedelta(minutes=minutes),
        role=role,
        banner_suitability=0.5,
        names=tuple(names),
        summary=summary,
    )


def _jpeg(width=1200, height=700) -> bytes:
    out = io.BytesIO()
    Image.new('RGB', (width, height), (40, 90, 160)).save(out, format='JPEG')
    return out.getvalue()


class TestFrameNames:
    def test_owner_tile_and_ai_agents_never_become_participants(self):
        evidence = [
            _evidence('a', 1, ['Jordan Rivera', 'You', 'Boardy Boardman', 'Fireflies Notetaker']),
            _evidence('b', 5, ['Jordan Rivera (Presenting)', 'Omi Agent', 'ash@fulcra.com']),
        ]
        assert screen_frame_names(evidence) == ['Jordan Rivera']

    def test_most_frequent_first_and_deduplicated(self):
        evidence = [_evidence('a', 1, ['Priya Natarajan', 'Jordan Rivera']), _evidence('b', 2, ['Jordan  Rivera'])]
        assert screen_frame_names(evidence) == ['Jordan Rivera', 'Priya Natarajan']


class TestRosterEnrichment:
    def test_frames_alone_create_a_screen_activity_context(self):
        context = with_screen_frame_participants(None, ['Jordan Rivera'], started_at=START, duration_minutes=30)
        assert context is not None
        assert context.calendar_source == 'screen_activity'
        assert [p.name for p in context.participants] == ['Jordan Rivera']

    def test_a_name_the_calendar_already_has_is_not_duplicated(self):
        calendar = CalendarMeetingContext(
            calendar_event_id='evt',
            title='Sync',
            participants=[MeetingParticipant(name='Jordan Rivera', email='jordan@acme.com')],
            start_time=START,
            duration_minutes=30,
            calendar_source='google',
        )
        assert with_screen_frame_participants(calendar, ['Jordan Rivera'], started_at=START, duration_minutes=30) is (
            calendar
        )

    def test_a_shared_first_name_is_not_an_email_match(self):
        calendar = CalendarMeetingContext(
            calendar_event_id='evt',
            title='Sync',
            participants=[MeetingParticipant(email='john.smith@acme.com')],
            start_time=START,
            duration_minutes=30,
            calendar_source='google',
        )
        merged = with_screen_frame_participants(calendar, ['John Doe'], started_at=START, duration_minutes=30)
        assert [(p.name, p.email) for p in merged.participants] == [
            (None, 'john.smith@acme.com'),
            ('John Doe', None),
        ]

    def test_a_nameless_invitee_gets_the_tile_name_instead_of_a_twin(self):
        calendar = CalendarMeetingContext(
            calendar_event_id='evt',
            title='Sync',
            participants=[MeetingParticipant(email='jordan.rivera@acme.com')],
            start_time=START,
            duration_minutes=30,
            calendar_source='google',
        )
        merged = with_screen_frame_participants(calendar, ['Jordan Rivera'], started_at=START, duration_minutes=30)
        assert [(p.name, p.email) for p in merged.participants] == [('Jordan Rivera', 'jordan.rivera@acme.com')]
        assert merged.calendar_source == 'google'


class TestSpeakerBindingWithScreenRoster:
    """conversation_prompt_prefix binds the one remote voice to the one remote human."""

    def _prefix(self, names, extra_participants=()):
        from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix

        context = with_screen_frame_participants(
            (
                CalendarMeetingContext(
                    calendar_event_id='screen-activity',
                    title='Meet - abc-defg-hij',
                    participants=list(extra_participants),
                    start_time=START,
                    duration_minutes=30,
                    calendar_source='screen_activity',
                )
                if extra_participants
                else None
            ),
            names,
            started_at=START,
            duration_minutes=30,
        )
        roster = normalize_meeting_participants(context, 'desktop', 'David Zhang', ['david@example.com'], [])
        return build_conversation_prompt_prefix(
            conversation_id='c',
            transcript='[s1 0] hi\n[s2 1] hello',
            started_at=START,
            timezone_name='UTC',
            language_code='en',
            calendar_context=context,
            speaker_map={0: 'David Zhang', 1: None},
            roster=roster,
            desktop_meeting_capture=True,
        )

    def test_one_screen_derived_human_names_the_remote_voice(self):
        prefix = self._prefix(screen_frame_names([_evidence('a', 1, ['Jordan Rivera', 'You'])]))
        assert 'spk 1 Jordan Rivera' in prefix.context
        assert '- Jordan Rivera | - | human | via screen_activity' in prefix.context

    def _frame_roster_names(self, names):
        evidence = [_evidence('a', 1, names)]
        return screen_frame_names(evidence) + screen_frame_agent_names(evidence)

    def test_a_speaking_agent_tile_keeps_the_ambiguity_guard(self):
        # Boardy talks on calls: with Jordan and Boardy on screen the remote channel may be
        # either, so it must not bind to the one visible human.
        prefix = self._prefix(self._frame_roster_names(['Jordan Rivera', 'Boardy Boardman']))
        assert 'spk 1 Jordan Rivera' not in prefix.context
        assert '- Boardy Boardman | - | ai agent | via screen_activity' in prefix.context

    def test_a_silent_notetaker_tile_does_not_block_binding(self):
        # Incident 449565eb: a NoteTaker bot records and never speaks, so the one remote
        # voice is the one remote human.
        prefix = self._prefix(self._frame_roster_names(['Tristan Jensen', 'You', 'Tomorrow Inc - NoteTaker']))
        assert 'spk 1 Tristan Jensen' in prefix.context
        assert '- Tomorrow Inc - NoteTaker | - | ai agent | via screen_activity' in prefix.context

    def test_an_agent_the_roster_would_not_classify_is_not_added(self):
        # "Read Ai" trips the tile marker but not the roster catalog; adding it would make a human.
        assert screen_frame_agent_names([_evidence('a', 1, ['Read Ai'])]) == []

    def test_an_ai_agent_already_on_the_roster_still_blocks_the_guess(self):
        # Boardy on the OCR roster may be the remote voice: no binding.
        prefix = self._prefix(['Jordan Rivera'], extra_participants=[MeetingParticipant(name='Boardy Boardman')])
        assert 'spk 1 Jordan Rivera' not in prefix.context
        assert '| ai agent |' in prefix.context


class TestScreenMoments:
    def test_lines_carry_offsets_summaries_and_names(self):
        lines = screen_moment_lines(
            [
                _evidence('a', 2, ['Jordan Rivera'], 'Google Meet call with Jordan Rivera'),
                _evidence('b', 14.5, [], 'Shared slide "Q3 roadmap": three launch dates'),
                _evidence('c', 20, [], ''),
            ],
            START,
        )
        assert lines == (
            '- [+02:00] Google Meet call with Jordan Rivera (on screen: Jordan Rivera)',
            '- [+14:30] Shared slide "Q3 roadmap": three launch dates',
        )

    def test_moments_render_inside_the_pack_budget_before_raw_screen_text(self):
        pack = MeetingContextPack(
            screen_moments=tuple(f'- [+{i:02d}:00] ' + 'summary ' * 40 for i in range(7)),
            screen_text='ocr ' * 2000,
        )
        rendered = render_meeting_context_pack(pack)
        assert len(rendered) <= MAX_CONTEXT_PACK_CHARACTERS
        assert rendered.index('SCREEN MOMENTS') < rendered.index('SCREEN ACTIVITY')
        moments = rendered.split('SCREEN MOMENTS', 1)[1].split('SCREEN ACTIVITY', 1)[0]
        assert len(moments) < 1_000

    def test_moments_alone_make_a_pack(self):
        assert not MeetingContextPack(screen_moments=('- [+00:10] Meet',)).empty


class TestEnvironmentScopedReads:
    @pytest.fixture(autouse=True)
    def _setting_on(self, monkeypatch):
        monkeypatch.setattr(evidence_mod, 'get_meeting_note_screenshots_enabled', lambda uid: True)

    def test_account_setting_off_means_no_evidence_and_no_frame_read(self, monkeypatch):
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)
        monkeypatch.setattr(evidence_mod, 'get_meeting_note_screenshots_enabled', lambda uid: False)

        def boom(*_):
            raise AssertionError('hidden screenshots must not be read for notes')

        monkeypatch.setattr(evidence_mod, 'get_conversation_screen_frames', boom)
        assert load_screen_frame_evidence('u', 'c') == ()

    def test_only_this_environments_frames_are_evidence(self, monkeypatch):
        docs = [
            {'id': 'dev', 'captured_at': START, 'visible_participant_names': ['Dev Person'], 'screen_summary': 's'},
            {'id': 'prod', 'captured_at': START, 'storage_bucket': PROD, 'visible_participant_names': ['Jo Ro']},
        ]
        monkeypatch.setattr(evidence_mod, 'get_conversation_screen_frames', lambda *_: docs)
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)
        assert [item.frame_id for item in load_screen_frame_evidence('u', 'c')] == ['prod']
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', DEV)
        assert [item.frame_id for item in load_screen_frame_evidence('u', 'c')] == ['dev']

    def test_no_bucket_means_no_evidence_and_no_read(self, monkeypatch):
        monkeypatch.delenv('BUCKET_SCREEN_FRAMES', raising=False)
        monkeypatch.setattr('utils.other.storage.screen_frames_bucket', None)

        def boom(*_):
            raise AssertionError('must not read frames without a bucket')

        monkeypatch.setattr(evidence_mod, 'get_conversation_screen_frames', boom)
        assert load_screen_frame_evidence('u', 'c') == ()


class TestFrameImages:
    def test_up_to_four_downscaled_frames_with_the_banner_included(self, monkeypatch):
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)
        reads: list[str] = []

        def download(uid, cid, frame_id, *, timeout):
            assert timeout <= evidence_mod.FRAME_READ_TIMEOUT_SECONDS
            reads.append(frame_id)
            return _jpeg()

        monkeypatch.setattr(evidence_mod, 'download_screen_frame_bytes', download)
        evidence = [_evidence(f'f{i}', i) for i in range(6)] + [_evidence('banner', 30, role='banner')]

        images = load_notes_frame_images('u', 'c', evidence, START)

        assert len(images) == 4 and 'banner' in reads
        for image in images:
            raw = __import__('base64').b64decode(image.data_url.split(',', 1)[1])
            with Image.open(io.BytesIO(raw)) as decoded:
                assert decoded.format == 'JPEG' and max(decoded.size) <= 1024

    def test_a_failed_read_is_skipped_not_fatal(self, monkeypatch):
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)

        def download(uid, cid, frame_id, *, timeout):
            if frame_id == 'bad':
                raise TimeoutError('slow bucket')
            return _jpeg(800, 600)

        monkeypatch.setattr(evidence_mod, 'download_screen_frame_bytes', download)
        images = load_notes_frame_images('u', 'c', [_evidence('bad', 1), _evidence('ok', 2)], START)
        assert [image.frame_id for image in images] == ['ok']

    def test_the_read_budget_bounds_total_time(self, monkeypatch):
        monkeypatch.setenv('BUCKET_SCREEN_FRAMES', PROD)
        clock = iter([0.0, 0.0, 7.0, 7.0, 7.0])
        monkeypatch.setattr(evidence_mod.time, 'monotonic', lambda: next(clock))
        monkeypatch.setattr(evidence_mod, 'download_screen_frame_bytes', lambda *a, **k: _jpeg(10, 10))
        images = load_notes_frame_images('u', 'c', [_evidence('a', 1), _evidence('b', 2)], START)
        assert [image.frame_id for image in images] == ['a']


FRAMES = (
    NotesFrameImage(frame_id='a', offset_label='+02:00', data_url='data:image/jpeg;base64,AAAA'),
    NotesFrameImage(frame_id='b', offset_label='+14:30', data_url='data:image/jpeg;base64,BBBB'),
)


def _wire_messages_for(client) -> list[dict]:
    from langchain_core.messages import SystemMessage

    payload = client._get_request_payload([SystemMessage(content='static'), screen_frames_message(FRAMES)])
    return payload['messages']


def _image_urls(message) -> list[str]:
    content = message['content'] if isinstance(message, dict) else message.content
    return [part['image_url']['url'] for part in content if isinstance(part, dict) and part.get('type') == 'image_url']


class TestImagesReachTheProvider:
    def _notes(self, monkeypatch, *, screen_frames, rich=True):
        from utils.llm import conversation_processing
        from utils.llm.conversation_prompt_context import ConversationPromptPrefix

        captured: dict = {}

        class Model:
            def invoke(self, messages):
                captured['messages'] = messages
                payload = {
                    'title': 'Sync',
                    'overview': 'o',
                    'emoji': '🧠',
                    'category': 'work',
                    'sections': [{'heading': 'Plan', 'body_markdown': '- Decided', 'kind': 'main'}],
                    'action_items': [],
                    'events': [],
                }
                return SimpleNamespace(content=json.dumps(payload))

        monkeypatch.setattr(conversation_processing, 'get_llm', lambda *_a, **_k: Model())
        monkeypatch.setattr(conversation_processing, 'shared_conversation_cache_supported', lambda: False)
        conversation_processing.get_conversation_notes(
            ConversationPromptPrefix(conversation_id='c', context='CONVERSATION METADATA\n\nFULL TRANSCRIPT\nhello'),
            started_at=START,
            language_code='en',
            output_language_code='en',
            tz='UTC',
            task_intelligence_capture=False,
            rich_context_enabled=rich,
            roster=None,
            screen_frames=screen_frames,
        )
        return captured['messages']

    def test_the_notes_call_carries_every_frame_as_an_image_part(self, monkeypatch):
        messages = self._notes(monkeypatch, screen_frames=FRAMES)
        assert _image_urls(messages[-1]) == [frame.data_url for frame in FRAMES]

    def test_no_frames_means_no_extra_message(self, monkeypatch):
        messages = self._notes(monkeypatch, screen_frames=())
        assert all(not _image_urls(message) for message in messages)

    def test_the_legacy_prompt_never_carries_frames(self, monkeypatch):
        messages = self._notes(monkeypatch, screen_frames=FRAMES, rich=False)
        assert all(not _image_urls(message) for message in messages)

    def _wire_messages(self, client) -> list[dict]:
        return _wire_messages_for(client)

    def test_direct_openai_payload_keeps_the_image_parts(self):
        wire = self._wire_messages(_CLIENTS['direct'])
        assert wire[-1]['role'] == 'user'
        assert _image_urls(wire[-1]) == [frame.data_url for frame in FRAMES]

    def test_gateway_hop_keeps_the_image_parts_to_the_provider(self):
        from llm_gateway.gateway.executor import provider_request_for
        from llm_gateway.gateway.resolver import resolve_chat_completion_route

        wire = self._wire_messages(_CLIENTS['gateway'])
        assert _image_urls(wire[-1]) == [frame.data_url for frame in FRAMES]

        config = _GATEWAY_CONFIG[0]
        resolved = resolve_chat_completion_route(config, {'model': 'omi:auto:conv-structure', 'messages': wire})
        route = resolved.active_route
        for provider_ref in [route.primary, *getattr(route, 'fallbacks', [])]:
            provider_request = provider_request_for(resolved, provider_ref)
            assert _image_urls(provider_request['messages'][-1]) == [frame.data_url for frame in FRAMES], provider_ref


class TestWiringFlags:
    """Names/moments ride MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED; images need their own flag."""

    def _run(self, monkeypatch, *, screen_text, frames):
        from utils.conversations import meeting_notes_wiring as wiring

        monkeypatch.setenv('MEETING_NOTES_SCREEN_TEXT_CONTEXT_ENABLED', 'true' if screen_text else 'false')
        monkeypatch.setenv('MEETING_NOTES_SCREEN_FRAMES_CONTEXT_ENABLED', 'true' if frames else 'false')
        evidence = (_evidence('a', 2, ['Jordan Rivera'], 'Google Meet call'),)
        loaded: list[str] = []
        monkeypatch.setattr(wiring, 'load_screen_frame_evidence', lambda uid, cid: loaded.append(cid) or evidence)
        monkeypatch.setattr(wiring, 'load_notes_frame_images', lambda *a: FRAMES)
        captured: dict = {}

        def pack(uid, conversation, roster, **kwargs):
            captured.update(kwargs)
            return None

        sources = SimpleNamespace(
            load_people_documents=lambda uid: [],
            resolve_owner_identity=lambda uid: ('David Zhang', ('david@example.com',)),
            gather_meeting_context_pack=pack,
        )
        monkeypatch.setattr(wiring, 'meeting_context_sources', lambda: sources)
        conversation = SimpleNamespace(
            id='conv-1',
            source='desktop',
            external_data={'conversation_role': 'meeting'},
            started_at=START,
            finished_at=START + timedelta(minutes=30),
            transcript_segments=[],
        )
        roster, _block, _desktop, images = wiring.rich_notes_inputs(
            'u', conversation, None, 'UTC', include_background=True, include_screen_text=screen_text
        )
        names = [entry.display_name for entry in roster.entries if entry.kind == 'human']
        return names, images, captured.get('screen_moments'), loaded

    def test_everything_off_reads_no_frames(self, monkeypatch):
        names, images, moments, loaded = self._run(monkeypatch, screen_text=False, frames=False)
        assert (names, images, moments, loaded) == ([], (), (), [])

    def test_screen_text_flag_adds_names_and_moments_but_no_images(self, monkeypatch):
        names, images, moments, _loaded = self._run(monkeypatch, screen_text=True, frames=False)
        assert names == ['Jordan Rivera'] and images == ()
        assert moments == ('- [+02:00] Google Meet call (on screen: Jordan Rivera)',)

    def test_frames_flag_alone_attaches_images_only(self, monkeypatch):
        names, images, moments, _loaded = self._run(monkeypatch, screen_text=False, frames=True)
        # The image-derived names still reach the roster, so the notes validator keeps them.
        assert names == ['Jordan Rivera'] and images == FRAMES and moments == ()
