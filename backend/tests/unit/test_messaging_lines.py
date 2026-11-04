"""New links spread across phone lines. Transactions run on a local Firestore emulator only."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from config.messaging import ChannelLine, channel_lines, public_link_fields
from database.messaging_lines import _room
from testing.messaging.loopback import LoopbackAdapter
from utils.messaging.access import SeatFull
from utils.messaging.identity import key

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def configure(monkeypatch, *lines):
    monkeypatch.setenv(
        'OMI_MESSAGING_LINK_TARGETS',
        json.dumps({'imessage': {'provider': 'linq', 'address': lines[0]['address'], 'lines': list(lines)}}),
    )


def test_config_reads_defaults_and_leaves_closed_lines_out(monkeypatch):
    configure(
        monkeypatch,
        {'address': '+1001'},
        {'address': '+1002', 'max_users': 200, 'new_per_day': 20, 'started': '2026-11-01'},
        {'address': '+1003', 'enabled': False},
    )
    assert channel_lines('imessage') == (
        ChannelLine('+1001', 400, 40, None),
        ChannelLine('+1002', 200, 20, date(2026, 11, 1)),
    )
    assert channel_lines('telegram') is None


def test_every_line_closed_is_different_from_no_lines(monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'enabled': False})
    assert channel_lines('imessage') == ()


@pytest.mark.parametrize(
    'lines',
    [
        [],
        'x',
        [{'max_users': 3}],
        [{'address': ''}],
        [{'address': 'a/b'}],
        [{'address': '+1', 'max_users': '3'}],
        [{'address': '+1', 'new_per_day': -1}],
        [{'address': '+1', 'started': 'soon'}],
        [{'address': '+1'}, {'address': '+1'}],
        [{'address': '+1', 'enabled': 'false'}],
    ],
)
def test_malformed_lines_close_linking_instead_of_lifting_the_limits(monkeypatch, lines):
    monkeypatch.setenv('OMI_MESSAGING_LINK_TARGETS', json.dumps({'imessage': {'address': '+1', 'lines': lines}}))
    assert channel_lines('imessage') == ()


def test_malformed_targets_mean_no_lines(monkeypatch):
    monkeypatch.setenv('OMI_MESSAGING_LINK_TARGETS', '{')
    assert channel_lines('imessage') is None
    monkeypatch.delenv('OMI_MESSAGING_LINK_TARGETS')
    assert channel_lines('imessage') is None


def test_new_line_grows_weekly_up_to_its_limit():
    line = ChannelLine('+1', started=date(2026, 11, 1))
    assert line.new_limit(date(2026, 10, 31)) == 0
    assert line.new_limit(date(2026, 11, 1)) == 10
    assert line.new_limit(date(2026, 11, 7)) == 10
    assert line.new_limit(date(2026, 11, 8)) == 20
    assert line.new_limit(date(2026, 11, 22)) == 40
    assert line.new_limit(date(2027, 11, 1)) == 40
    assert ChannelLine('+1').new_limit(date(2026, 11, 1)) == 40
    assert replace(line, new_per_day=15).new_limit(date(2026, 12, 1)) == 15


def test_room_is_the_tighter_limit_and_pending_people_take_user_room():
    line = ChannelLine('+1', max_users=10, new_per_day=4)
    assert _room(line, {'users': 5}, {}, 'me', NOW) == 0.5
    linked = {'a': {'linked': True}, 'b': {'linked': True}, 'c': {'linked': True}}
    assert _room(line, {'users': 0}, linked, 'me', NOW) == 0.25
    assert _room(line, {'users': 9}, {'a': {'linked': False}}, 'me', NOW) == 0
    assert _room(line, {'users': 9}, {'me': {'linked': False}}, 'me', NOW) == 0.1
    assert _room(ChannelLine('+1', max_users=0), {}, {}, 'me', NOW) == 0


@pytest.fixture
def store(monkeypatch):
    host = os.getenv('MESSAGING_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Loopback emulator not requested')
    assert host.startswith('127.0.0.1:')
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from database.messaging import MessagingStore

    os.environ['FIRESTORE_EMULATOR_HOST'] = host
    monkeypatch.setenv('OMI_MESSAGING_CHANNEL_POLICY', '{"imessage":{"enabled":true,"cohort":"*","seat_cap":"off"}}')
    client = firestore.Client(project='demo-lines-' + uuid4().hex[:10], credentials=AnonymousCredentials())
    instance = MessagingStore(firestore_client=client)
    for index in range(200):
        client.collection('users').document(f'u{index}').set({'name': 'synthetic'})
    yield instance
    client.close()


def mint(store, uid, now=NOW):
    return store.mint(uid, 'imessage', 'linq', 'code', now=now)


def link(store, uid, proof, sender=None, now=NOW):
    adapter = LoopbackAdapter()
    message = replace(
        adapter.parse(adapter.signed()[0])[0],
        channel='imessage',
        provider='linq',
        external_user_id=sender or 'phone-' + uid,
    )
    return message, store.consume(proof, message, now=now)


def line_row(store, address):
    return store.capacity('imessage').collection('lines').document(address).get().to_dict() or {}


def test_one_line_serves_everyone_until_its_daily_limit(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'new_per_day': 2})
    for uid in ('u0', 'u1'):
        minted = mint(store, uid)
        assert minted['address'] == '+1001'
        link(store, uid, minted['proof'])
    assert line_row(store, '+1001')['users'] == 2
    with pytest.raises(SeatFull):
        mint(store, 'u2')
    assert store.user('u2').collection('channel_waitlist').document('imessage').get().exists
    assert mint(store, 'u2', now=NOW + timedelta(hours=25))['address'] == '+1001'


def test_new_links_spread_evenly_across_lines(store, monkeypatch):
    configure(monkeypatch, *[{'address': f'+100{index}'} for index in range(3)])
    for index in range(12):
        uid = f'u{index}'
        link(store, uid, mint(store, uid)['proof'])
    assert [line_row(store, f'+100{index}')['users'] for index in range(3)] == [4, 4, 4]


def test_a_fresh_line_does_not_take_the_whole_wave(store, monkeypatch):
    configure(
        monkeypatch,
        {'address': '+1001'},
        {'address': '+1002', 'started': NOW.date().isoformat(), 'new_per_day': 40},
    )
    for index in range(12):
        uid = f'u{index}'
        link(store, uid, mint(store, uid)['proof'])
    assert line_row(store, '+1002')['users'] <= 10
    assert line_row(store, '+1001')['users'] >= 2


def test_many_lines_read_samples_and_still_find_the_last_free_line(store, monkeypatch):
    lines = [{'address': f'+2{index:03}', 'new_per_day': 0} for index in range(30)]
    lines[17]['new_per_day'] = 1
    configure(monkeypatch, *lines)
    assert mint(store, 'u0')['address'] == '+2017'
    with pytest.raises(SeatFull):
        mint(store, 'u1')


def test_a_new_code_keeps_the_line_and_one_slot(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'new_per_day': 1}, {'address': '+1002', 'new_per_day': 1})
    first = mint(store, 'u0')['address']
    assert mint(store, 'u0', now=NOW + timedelta(minutes=1))['address'] == first
    assert len(line_row(store, first)['starts']) == 1


def test_an_abandoned_code_gives_its_slot_back(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'new_per_day': 1})
    mint(store, 'u0')
    with pytest.raises(SeatFull):
        mint(store, 'u1', now=NOW + timedelta(minutes=9))
    assert mint(store, 'u1', now=NOW + timedelta(minutes=11))['address'] == '+1001'
    assert list(line_row(store, '+1001')['starts']) == [key('u1')]


def test_simultaneous_codes_cannot_pass_the_limit(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'new_per_day': 5})

    def attempt(index):
        try:
            return mint(store, f'u{index}')['address']
        except SeatFull:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(12)))
    assert sum(result is not None for result in results) == 5
    assert len(line_row(store, '+1001')['starts']) == 5


def test_relinking_returns_to_the_same_line_without_a_new_slot(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'new_per_day': 1}, {'address': '+1002', 'new_per_day': 1})
    minted = mint(store, 'u0')
    message, _ = link(store, 'u0', minted['proof'])
    address = minted['address']
    other = '+1002' if address == '+1001' else '+1001'
    store.unlink('u0', key(message.channel, message.provider, message.external_user_id))
    assert line_row(store, address)['users'] == 0
    # Still spent for 24 hours: the line has already opened that conversation.
    assert len(line_row(store, address)['starts']) == 1
    assert mint(store, 'u1')['address'] == other
    again = mint(store, 'u0', now=NOW + timedelta(hours=1))
    assert again['address'] == address
    link(store, 'u0', again['proof'], now=NOW + timedelta(hours=1))
    assert line_row(store, address)['users'] == 1


def test_a_returning_person_keeps_their_line_even_when_it_has_filled(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001', 'max_users': 1})
    message, _ = link(store, 'u0', mint(store, 'u0')['proof'])
    store.unlink('u0', key(message.channel, message.provider, message.external_user_id))
    later = NOW + timedelta(hours=25)
    link(store, 'u1', mint(store, 'u1', now=later)['proof'], now=later)
    again = mint(store, 'u0', now=later)
    assert again['address'] == '+1001'
    link(store, 'u0', again['proof'], now=later)
    assert line_row(store, '+1001')['users'] == 2


def test_malformed_lines_put_people_on_the_waitlist(store, monkeypatch):
    monkeypatch.setenv('OMI_MESSAGING_LINK_TARGETS', json.dumps({'imessage': {'address': '+1', 'lines': 'x'}}))
    with pytest.raises(SeatFull):
        mint(store, 'u0')


def test_a_second_code_for_a_live_link_counts_once(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001'})
    _, row = link(store, 'u0', mint(store, 'u0')['proof'], sender='same')
    assert row['line'] == '+1001'
    _, row = link(store, 'u0', mint(store, 'u0')['proof'], sender='same')
    assert row['line'] == '+1001'
    assert line_row(store, '+1001')['users'] == 1


def test_a_closed_line_takes_nobody_new_and_keeps_its_people(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001'})
    message, _ = link(store, 'u0', mint(store, 'u0')['proof'])
    configure(monkeypatch, {'address': '+1002'}, {'address': '+1001', 'enabled': False})
    assert mint(store, 'u1')['address'] == '+1002'
    store.unlink('u0', key(message.channel, message.provider, message.external_user_id))
    assert line_row(store, '+1001')['users'] == 0
    assert mint(store, 'u0')['address'] == '+1002'


def test_link_from_before_lines_is_counted_on_its_next_code(store, monkeypatch):
    monkeypatch.delenv('OMI_MESSAGING_LINK_TARGETS', raising=False)
    minted = mint(store, 'u0')
    assert 'address' not in minted
    _, row = link(store, 'u0', minted['proof'], sender='same')
    assert 'line' not in row
    configure(monkeypatch, {'address': '+1001'})
    _, row = link(store, 'u0', mint(store, 'u0')['proof'], sender='same')
    assert row['line'] == '+1001'
    assert line_row(store, '+1001')['users'] == 1


def test_account_deletion_removes_the_placement_and_the_count(store, monkeypatch):
    configure(monkeypatch, {'address': '+1001'})
    link(store, 'u0', mint(store, 'u0')['proof'])
    store.delete_account('u0')
    assert line_row(store, '+1001')['users'] == 0
    assert not list(store.user('u0').collection('channel_lines').stream())


def test_public_fields_prefer_the_assigned_line(monkeypatch):
    monkeypatch.setenv(
        'OMI_MESSAGING_LINK_TARGETS',
        json.dumps({'imessage': {'address': '+1001', 'deep_link_template': 'sms:{address}?body={proof}'}}),
    )
    assert public_link_fields('imessage', 'CODE', address='+1002') == ('sms:%2B1002?body=CODE', '+1002')
