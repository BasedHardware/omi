"""Capture-group meeting identity: member contexts and the primary notes gap.

Owner meeting 2026-10-28: a pendant (ambient, longest window) became the capture
group primary, so the rendered row lost the named Meet participants and screen
evidence that lived on the hidden desktop meeting halves. These tests pin the
pure decisions that route member-held identity to the primary's notes.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from utils.conversations import capture_group_meeting_context as cg

T0 = datetime(2026, 10, 28, 4, 43, tzinfo=timezone.utc)


def context(names=(), event_id='evt-1', source='system_calendar', title='Weekly sync'):
    return CalendarMeetingContext(
        calendar_event_id=event_id,
        title=title,
        participants=[MeetingParticipant(name=name) for name in names],
        start_time=T0,
        duration_minutes=30,
        calendar_source=source,
    )


def stored(context_value):
    return {
        'visibility': 'shared',
        'external_data': {'calendar_meeting_context': context_value.model_dump(mode='json')},
    }


def group_record(primary, *members):
    return {
        'id': 'group-1',
        'primary_id': primary,
        'revision': 3,
        'members': [{'id': primary, 'source': 'omi', 'evidence': {'method': 'overlap_shared_speech_v1'}}]
        + [
            {'id': mid, 'source': source, 'evidence': {'method': 'overlap_shared_speech_v1'}} for mid, source in members
        ],
    }


def conversation(id='pendant', group=None):
    if group is not None:
        if not hasattr(group, 'id'):
            group.id = 'group-1'
        if not hasattr(group, 'primary_id'):
            group.primary_id = id
        if not hasattr(group, 'revision'):
            group.revision = 3
        for member in getattr(group, 'members', ()) or ():
            if not hasattr(member, 'evidence'):
                member.evidence = {'method': 'shared_speech'}
    return SimpleNamespace(id=id, capture_group=group)


class TestGroupMembers:
    def test_reads_model_and_raw_shapes_and_skips_empty_ids(self):
        model = conversation(
            group=SimpleNamespace(
                members=[SimpleNamespace(id='a', source='omi'), SimpleNamespace(id='b', source='desktop')]
            )
        )
        assert cg.group_members(model) == [{'id': 'a', 'source': 'omi'}, {'id': 'b', 'source': 'desktop'}]
        raw = {'capture_group': group_record('a', ('b', 'desktop'))}
        assert cg.group_members(raw) == [
            {'id': 'a', 'source': 'omi'},
            {'id': 'b', 'source': 'desktop'},
        ]
        broken = SimpleNamespace(id='x', capture_group=SimpleNamespace(members=[SimpleNamespace(id='', source=None)]))
        assert cg.group_members(broken) == []
        assert cg.group_members(SimpleNamespace(id='x')) == []

    def test_merged_member_contexts_unions_participants_in_record_order(self, monkeypatch):
        rows = {
            'half-b': stored(context(['Nik Shevchenko'])),
            'half-c': stored(context(['Ash Kalb'], event_id='evt-2', title='Meet - second half')),
        }
        monkeypatch.setattr(
            cg.conversations_db,
            'get_conversation_raw_snapshot',
            lambda uid, cid, field_paths=None, firestore_client=None: rows.get(cid),
        )
        merged = cg.merged_member_contexts(
            'u',
            conversation(
                group=SimpleNamespace(
                    members=[
                        SimpleNamespace(id='pendant', source='omi'),
                        SimpleNamespace(id='half-b', source='desktop'),
                        SimpleNamespace(id='half-c', source='desktop'),
                    ]
                )
            ),
        )
        assert merged is not None
        assert {p.name for p in merged.participants} == {'Nik Shevchenko', 'Ash Kalb'}
        assert merged.title == 'Weekly sync'  # first member context wins the scalars

    def test_merged_member_contexts_none_when_no_member_carries_one(self, monkeypatch):
        monkeypatch.setattr(
            cg.conversations_db,
            'get_conversation_raw_snapshot',
            lambda uid, cid, field_paths=None, firestore_client=None: {'external_data': {}},
        )
        assert (
            cg.merged_member_contexts(
                'u', conversation(group=SimpleNamespace(members=[SimpleNamespace(id='b', source='desktop')]))
            )
            is None
        )

    def test_member_read_failure_degrades_to_the_rest(self, monkeypatch):
        rows = {'half-b': stored(context(['Nik Shevchenko']))}

        def flaky(uid, cid, field_paths=None, firestore_client=None):
            if cid == 'half-c':
                raise RuntimeError('boom')
            return rows.get(cid)

        monkeypatch.setattr(cg.conversations_db, 'get_conversation_raw_snapshot', flaky)
        merged = cg.merged_member_contexts(
            'u',
            conversation(
                group=SimpleNamespace(
                    members=[
                        SimpleNamespace(id='half-b', source='desktop'),
                        SimpleNamespace(id='half-c', source='desktop'),
                    ]
                )
            ),
        )
        assert merged is not None and [p.name for p in merged.participants] == ['Nik Shevchenko']


class TestPrimaryNotesGap:
    def primary(self, own=None):
        row = {'id': 'pendant', 'status': 'completed', 'capture_group': group_record('pendant', ('half-b', 'desktop'))}
        if own is not None:
            row.update(stored(own))
        return row

    def member_rows(self, contexts):
        return {mid: stored(ctx) for mid, ctx in contexts.items()}

    def test_gap_when_primary_has_no_context_and_a_member_has_one(self):
        gap = cg.primary_notes_gap(
            self.primary(), self.member_rows({'half-b': context(['Nik Shevchenko'])}), has_new_meeting_evidence=True
        )
        assert gap is not None
        assert (gap.group_id, gap.revision, gap.primary_id) == ('group-1', 3, 'pendant')
        assert [p.name for p in gap.member_context.participants] == ['Nik Shevchenko']

    def test_gap_when_members_name_a_participant_the_primary_lacks(self):
        gap = cg.primary_notes_gap(
            self.primary(own=context(['Ash Kalb'])),
            self.member_rows({'half-b': context(['Ash Kalb', 'Nik Shevchenko'])}),
            has_new_meeting_evidence=True,
        )
        assert gap is not None

    def test_no_gap_when_primary_already_names_every_member_participant(self):
        primary = self.primary(own=context(['Ash Kalb', 'Nik Shevchenko']))
        primary['external_data'][cg.NOTES_REVISION_FIELD] = {'group_id': 'group-1', 'revision': 3}
        assert (
            cg.primary_notes_gap(
                primary,
                self.member_rows({'half-b': context(['Nik Shevchenko'])}),
            )
            is None
        )

    def test_no_gap_without_other_members_or_member_context(self):
        solo = {'id': 'pendant', 'capture_group': group_record('pendant')}
        assert cg.primary_notes_gap(solo, {}) is None
        assert cg.primary_notes_gap(self.primary(), {}) is None

    def test_no_gap_without_a_group_record(self):
        assert cg.primary_notes_gap({'id': 'pendant'}, {}) is None

    def test_frame_only_evidence_can_create_a_refresh_gap(self):
        gap = cg.primary_notes_gap(self.primary(), {}, has_new_meeting_evidence=True)
        assert gap is not None and gap.member_context is None

    def test_private_member_context_is_never_merged(self):
        private = stored(context(['Private participant']))
        private['visibility'] = 'private'
        confirmed = conversation(
            group=SimpleNamespace(
                members=[SimpleNamespace(id='pendant', source='omi'), SimpleNamespace(id='half-b', source='desktop')]
            )
        )
        assert cg.merged_member_contexts('u', confirmed, member_rows={'half-b': private}) is None

    def test_legacy_and_non_shared_speech_groups_are_not_eligible(self):
        legacy = self.primary()
        legacy['capture_group']['kind'] = 'desktop_pendant_call'
        assert (
            cg.primary_notes_gap(legacy, self.member_rows({'half-b': context(['Nik'])}), has_new_meeting_evidence=True)
            is None
        )
        legacy['capture_group'].pop('kind')
        legacy['capture_group']['members'][1]['evidence']['method'] = 'capture_containment_v1'
        assert (
            cg.primary_notes_gap(legacy, self.member_rows({'half-b': context(['Nik'])}), has_new_meeting_evidence=True)
            is None
        )


class TestKillSwitch:
    def test_off_disables_member_context_reads(self, monkeypatch):
        monkeypatch.setenv(cg.KILL_SWITCH_ENV, 'off')
        monkeypatch.setattr(cg, 'member_context_rows', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('read')))
        assert cg.merged_member_contexts('u', conversation()) is None

    def test_on_by_default_and_off_only_when_set_off(self, monkeypatch):
        monkeypatch.delenv(cg.KILL_SWITCH_ENV, raising=False)
        assert cg.capture_group_primary_notes_enabled() is True
        for off in ('0', 'false', 'off', 'no', 'OFF'):
            monkeypatch.setenv(cg.KILL_SWITCH_ENV, off)
            assert cg.capture_group_primary_notes_enabled() is False
        monkeypatch.setenv(cg.KILL_SWITCH_ENV, 'true')
        assert cg.capture_group_primary_notes_enabled() is True


class TestSyncDispatch:
    def test_dispatch_offers_the_finalized_row_and_swallows_errors(self, monkeypatch):
        from types import SimpleNamespace as NS

        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            cg,
            'import_module',
            lambda name: NS(refresh_primary_notes=lambda uid, cid: calls.append((uid, cid))),
        )
        cg.dispatch_primary_notes_refresh('u', NS(id='pendant'))
        assert calls == [('u', 'pendant')]

        def explode(name):
            raise RuntimeError('import down')

        monkeypatch.setattr(cg, 'import_module', explode)
        cg.dispatch_primary_notes_refresh('u', NS(id='pendant'))  # never raises

    def test_dispatch_skips_rows_without_an_id(self, monkeypatch):
        from types import SimpleNamespace as NS

        def explode(name):
            raise AssertionError('must not load the refresh module')

        monkeypatch.setattr(cg, 'import_module', explode)
        cg.dispatch_primary_notes_refresh('u', NS(id=None))
