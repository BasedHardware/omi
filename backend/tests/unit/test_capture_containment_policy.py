"""Containment-mode policy through the real ``link_duplicate_captures`` seam.

StrictFirestore fronts every lazy database getter, so no Google client is
constructed. The complementary fixture is tuned so the shipped symmetric
trigram rule stays false (8 < 15 shared trigrams) while token coverage stays
at 0.8125 >= 0.8; only the new detector can authorize the join.
"""

import json
import logging
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
import yaml

from database import capture_groups as groups_db
from database import conversations as conversations_db
from models.conversation import Conversation
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import capture_containment as containment_module
from utils.conversations import capture_jev_shadow as shadow
from utils.conversations import duplicate_capture as policy
from utils.conversations.shared_speech import measure_shared_speech

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
UID = 'synthetic-containment-user'

UTTERANCES = [
    'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa',
    'quartz jasper onyx topaz garnet opal pearl ruby amber coral ivory slate flint agate basalt cedar',
    'willow birch maple oak pine spruce hemlock alder aspen beech elm fir larch rowan poplar yew',
    'violet indigo cobalt umber sienna ocher mauve teal cyan fuchsia beige khaki lilac maroon navy plum',
]
UTTERANCE_TIMES = [80.0, 140.0, 200.0, 260.0]
REMOTE_FILLER = 'remote voice filler jargon aside tangent remark aside ' * 3

LEGACY_TEXT = (
    'we should ship the pendant firmware before the trade show and then fix the battery drain '
    'on the charging case because customers keep reporting that it dies overnight in the drawer '
    'also the factory wants a deposit by friday so finance needs the purchase order today'
)


def transcript_variant(text):
    """Sparse ASR noise: three substitutions plus two insertions per utterance."""
    words = text.split()
    words[4], words[8], words[12] = 'zzzfive', 'zzznine', 'zzzthirteen'
    words.insert(7, 'hum')
    words.insert(2, 'uh')
    return ' '.join(words)


def segment(text, start, is_user=True, end=None, **extra):
    return {
        'text': text,
        'start': start,
        'end': start + 12.0 if end is None else end,
        'is_user': is_user,
        'speaker': 'SPEAKER_00',
        **extra,
    }


def row(id, source, start=0, end=600, segments=None, **extra):
    return {
        'id': id,
        'source': source,
        'status': 'completed',
        'discarded': False,
        'started_at': T0 + timedelta(seconds=start),
        'finished_at': T0 + timedelta(seconds=end),
        'created_at': T0,
        'structured': {},
        'transcript_segments': segments if segments is not None else [],
        'external_data': {},
        **extra,
    }


def path(id, uid=UID):
    return ('users', uid, 'conversations', id)


def complementary_rows():
    """Pendant heard only the wearer; the laptop also heard remote participants."""
    pendant_segments = [segment(text, start) for text, start in zip(UTTERANCES, UTTERANCE_TIMES)]
    laptop_segments = []
    for index, (text, start) in enumerate(zip(UTTERANCES, UTTERANCE_TIMES)):
        laptop_segments.append(segment(transcript_variant(text), start + 3.0))
        if index < len(UTTERANCES) - 1:
            laptop_segments.append(segment(REMOTE_FILLER, start + 11.0, is_user=False, end=start + 31.0))
    laptop_segments.sort(key=lambda item: item['start'])
    return (
        row('pendant', 'omi', 0, 300, pendant_segments),
        row('laptop', 'desktop', -3, 300, laptop_segments),
    )


@pytest.fixture
def seam(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)

    def query(uid, *, status, finished_after, limit):
        rows = [
            deepcopy(r)
            for p, r in store.rows.items()
            if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
        ]
        return sorted(rows, key=lambda r: r['finished_at'])[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    events = []
    monkeypatch.setattr(policy, 'record_product_event', lambda event, **kw: events.append((event, kw.get('outcome'))))
    monkeypatch.setattr(policy, 'submit_same_scene', lambda *args: None)
    monkeypatch.setattr(policy, 'submit_resummary', lambda *args: None)
    return {'store': store, 'events': events}


def containment_lines(caplog):
    return [r.message for r in caplog.records if 'event=capture_group_containment' in r.message]


def test_complementary_pair_baseline_symmetric_rule_cannot_confirm():
    pendant, laptop = complementary_rows()
    shared = measure_shared_speech(pendant['transcript_segments'], laptop['transcript_segments'])
    assert not shared.confirms() and shared.shared_trigrams < 15


@pytest.mark.parametrize('last', ['pendant', 'laptop'])
def test_on_mode_joins_the_complementary_pair_with_containment_evidence(seam, monkeypatch, last, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    before = deepcopy(seam['store'].rows)
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path(last)]))
    record = seam['store'].rows[path('pendant')].get('capture_group')
    assert record and record == seam['store'].rows[path('laptop')].get('capture_group')
    assert {m['id'] for m in record['members']} == {'pendant', 'laptop'}
    methods = {m['evidence']['method'] for m in record['members']}
    assert methods == {'user_speech_containment'}
    assert ('capture_group_joined', 'applied') in seam['events']
    lines = containment_lines(caplog)
    assert all(token not in '\n'.join(lines) for token in (UID, 'pendant', 'laptop', 'alpha', 'bravo'))
    assert len(lines) == 1
    assert lines[0] == (
        'event=capture_group_containment mode=on phase=rule would_join=true ' 'reason=contained jev_p=unavailable'
    )
    for cid in ('pendant', 'laptop'):
        strip = {k: v for k, v in seam['store'].rows[path(cid)].items() if k != 'capture_group'}
        original = {k: v for k, v in before[path(cid)].items() if k != 'external_data'}
        assert {k: v for k, v in strip.items() if k != 'external_data'} == original
    for cid in ('pendant', 'laptop'):
        assert seam['store'].rows[path(cid)]['transcript_segments'] == before[path(cid)]['transcript_segments']
        assert seam['store'].rows[path(cid)]['structured'] == before[path(cid)]['structured']


def test_sparse_matches_with_long_span_do_not_group(seam, monkeypatch):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    pendant, laptop = complementary_rows()
    for record in (pendant, laptop):
        for item in record['transcript_segments']:
            if item.get('is_user'):
                item['end'] = item['start'] + 8.0
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())


def test_shadow_computes_and_logs_without_grouping(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'shadow')
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    before = deepcopy(seam['store'].rows)
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']
    assert sum(len(t.updates) for t in seam['store'].transactions) == 1
    lines = containment_lines(caplog)
    assert len(lines) == 1 and 'mode=shadow' in lines[0] and 'would_join=true' in lines[0]
    assert UID not in lines[0] and 'pendant' not in lines[0] and 'laptop' not in lines[0]
    for cid in ('pendant', 'laptop'):
        after = {k: v for k, v in seam['store'].rows[path(cid)].items() if k != 'external_data'}
        prior = {k: v for k, v in before[path(cid)].items() if k != 'external_data'}
        assert after == prior


def test_off_mode_never_measures_or_logs(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'off')
    detector = MagicMock(side_effect=AssertionError('detector must not run'))
    monkeypatch.setattr(policy, 'measure_capture_containment', detector)
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    detector.assert_not_called()
    assert not containment_lines(caplog)
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']


def test_mode_defaults_to_shadow_and_unknown_values_disable(monkeypatch):
    monkeypatch.delenv(containment_module.MODE_ENV, raising=False)
    assert containment_module.capture_group_containment_mode() == 'shadow'
    monkeypatch.setenv(containment_module.MODE_ENV, 'shaow')
    assert containment_module.capture_group_containment_mode() == 'off'
    monkeypatch.setenv(containment_module.MODE_ENV, '')
    assert containment_module.capture_group_containment_mode() == 'off'


def test_runtime_mode_change_is_honored_between_calls(seam, monkeypatch):
    monkeypatch.delenv(containment_module.MODE_ENV, raising=False)
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert 'capture_group' not in seam['store'].rows[path('pendant')]
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('pendant')]))
    assert seam['store'].rows[path('pendant')].get('capture_group')


def test_unrelated_user_meetings_stay_separate_in_on_mode(seam, monkeypatch):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    pendant, _ = complementary_rows()
    stranger = row(
        'stranger',
        'desktop',
        -3,
        300,
        [
            segment(
                'the quarterly numbers came in above forecast because renewals held up better '
                'than we modeled and finance still wants a slower hiring plan next quarter',
                83.0,
                end=113.0,
            ),
            segment(
                'okay yeah right the support team roadmap shifts again after the board meeting '
                'closes and recruiting pauses while the budget review wraps up this week',
                203.0,
                end=233.0,
            ),
        ],
    )
    seam['store'].rows.update({path('pendant'): pendant, path('stranger'): stranger})
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('stranger')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']


def test_background_media_without_user_speech_stays_separate(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    pendant, laptop = complementary_rows()
    for item in laptop['transcript_segments']:
        if not item['is_user']:
            item['start'] += 5.0
        item['is_user'] = False
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'none') in seam['events']
    assert any('reason=no_user_speech' in line for line in containment_lines(caplog))


@pytest.mark.parametrize('mode', ['off', 'shadow', 'on'])
def test_symmetric_confirmation_is_unchanged_in_every_mode(seam, monkeypatch, mode, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, mode)
    detector = MagicMock(side_effect=RuntimeError('PRIVATE-SENTINEL'))
    monkeypatch.setattr(policy, 'measure_capture_containment', detector)
    legacy = [{'text': LEGACY_TEXT, 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0.0, 'end': 60.0}]
    seam['store'].rows.update(
        {
            path('pendant'): row('pendant', 'omi', 0, 600, legacy),
            path('desktop'): row('desktop', 'desktop', 100, 590, legacy),
        }
    )
    with caplog.at_level(logging.INFO):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('desktop')]))
    if mode == 'off':
        detector.assert_not_called()
    else:
        detector.assert_called_once()
    record = seam['store'].rows[path('pendant')].get('capture_group')
    assert record and record == seam['store'].rows[path('desktop')].get('capture_group')
    assert {m['evidence']['method'] for m in record['members']} == {'shared_speech'}
    assert all('PRIVATE-SENTINEL' not in r.message for r in caplog.records)


@pytest.mark.parametrize('mutation', ['transcript', 'window'])
def test_containment_join_is_fenced_by_fingerprint_and_window(seam, monkeypatch, mutation):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    original = groups_db.join_capture_group

    def race(*args, **kwargs):
        if mutation == 'transcript':
            seam['store'].rows[path('pendant')]['transcript_segments'] = [
                segment('totally unrelated words now replace the transcript entirely', 10.0)
            ]
        else:
            seam['store'].rows[path('pendant')]['finished_at'] += timedelta(seconds=1)
        return original(*args, **kwargs)

    monkeypatch.setattr(groups_db, 'join_capture_group', race)
    policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert ('capture_group_joined', 'conflict') in seam['events']


def test_detector_fault_never_leaks_or_inhibits(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    monkeypatch.setattr(policy, 'measure_capture_containment', MagicMock(side_effect=RuntimeError('PRIVATE-SENTINEL')))
    fallback = MagicMock()
    monkeypatch.setattr(policy, 'record_fallback', fallback)
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    fallback.assert_called_once()
    assert ('capture_group_joined', 'none') in seam['events']
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    assert all('PRIVATE-SENTINEL' not in r.message for r in caplog.records)


def test_jev_success_logs_content_free_companion(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'shadow')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', UID)
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    pendant, laptop = complementary_rows()
    rows = {'pendant': pendant, 'laptop': laptop}
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')
    calls = []

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.75

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: calls.append(args) or Answer())
    emitted = []
    monkeypatch.setattr(shadow, '_record', lambda record: emitted.append(record))
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        shadow.submit_same_scene(UID, 'pendant', 'laptop')
    assert len(calls) == 1
    assert emitted[-1]['outcome'] == 'success' and emitted[-1]['p'] == 0.75
    lines = containment_lines(caplog)
    assert len(lines) == 1
    assert lines[0] == (
        'event=capture_group_containment mode=shadow phase=jev would_join=true ' 'reason=contained jev_p=0.750000'
    )
    assert UID not in lines[0] and 'pendant' not in lines[0]


def test_jev_companion_is_omitted_when_off(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'off')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', UID)
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    pendant, laptop = complementary_rows()
    rows = {'pendant': pendant, 'laptop': laptop}
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')
    detector = MagicMock(side_effect=AssertionError('detector must not run'))
    monkeypatch.setattr(shadow, 'measure_capture_containment', detector)

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.75

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: Answer())
    monkeypatch.setattr(shadow, '_record', lambda record: None)
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        shadow.submit_same_scene(UID, 'pendant', 'laptop')
    detector.assert_not_called()
    assert not containment_lines(caplog)


@pytest.mark.parametrize('mode', ['shadow', 'on'])
def test_pair_budget_exhaustion_blocks_join_through_the_seam(seam, monkeypatch, caplog, mode):
    monkeypatch.setenv(containment_module.MODE_ENV, mode)
    monkeypatch.setattr(containment_module, 'MAX_MATCHER_CALLS', 2)
    pendant, laptop = complementary_rows()
    seam['store'].rows.update({path('pendant'): pendant, path('laptop'): laptop})
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('laptop')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    for cid in ('pendant', 'laptop'):
        members = seam['store'].rows[path(cid)].get('capture_group', {}).get('members', [])
        assert all(m['evidence'].get('method') != 'user_speech_containment' for m in members)
    assert ('capture_group_joined', 'none') in seam['events']
    lines = containment_lines(caplog)
    assert any('would_join=false' in line and 'reason=bounds' in line for line in lines)


def test_pair_budget_exhaustion_bounds_every_candidate_pair(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'on')
    monkeypatch.setattr(containment_module, 'MAX_MATCHER_CALLS', 2)
    calls = []
    real = containment_module._ordered_match

    def spy(u_words, bundle_words):
        calls.append(1)
        return real(u_words, bundle_words)

    monkeypatch.setattr(containment_module, '_ordered_match', spy)
    pendant, _ = complementary_rows()
    seam['store'].rows[path('pendant')] = pendant
    for index in range(6):
        utterances = [
            segment('u%d w%d x%d y%d z%d v%d q%d r%d' % ((index,) * 8), t)
            for t in (20.0, 50.0, 80.0, 140.0, 200.0, 260.0)
        ]
        seam['store'].rows[path('stranger%d' % index)] = row('stranger%d' % index, 'desktop', 0, 300, utterances)
    with caplog.at_level(logging.INFO, logger=containment_module.logger.name):
        policy.link_duplicate_captures(UID, Conversation(**seam['store'].rows[path('pendant')]))
    assert all('capture_group' not in r for r in seam['store'].rows.values())
    lines = containment_lines(caplog)
    assert len(lines) == 6
    assert all('would_join=false' in line and 'reason=bounds' in line for line in lines)
    assert len(calls) <= 12
    assert all(token not in '\n'.join(lines) for token in (UID, 'pendant', 'stranger', 'alpha'))


REPO = Path(__file__).resolve().parents[3]
MODE_KEY = 'CAPTURE_GROUP_CONTAINMENT_MODE'
GKE_HOSTS = ('backend-listen', 'pusher')
CLOUD_RUN_HOSTS = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


def test_composed_manifest_declares_shadow_on_all_six_hosts_per_environment():
    manifest = yaml.safe_load((REPO / 'backend/deploy/runtime_env.yaml').read_text())
    for env_name in ('dev', 'prod'):
        env = manifest['environments'][env_name]
        for host in GKE_HOSTS:
            entry = env['gke'][host]['env'][MODE_KEY]
            assert entry == {'value': 'shadow', 'category': 'rollout'}, (env_name, host)
        for host in CLOUD_RUN_HOSTS:
            entry = env['cloud_run']['services'][host]['env'][MODE_KEY]
            assert entry == {'value': 'shadow', 'category': 'rollout'}, (env_name, host)


def test_gke_chart_values_match_the_composed_manifest():
    for chart in (
        'backend-listen/dev_omi_backend_listen_values.yaml',
        'backend-listen/prod_omi_backend_listen_values.yaml',
        'pusher/dev_omi_pusher_values.yaml',
        'pusher/prod_omi_pusher_values.yaml',
    ):
        values = yaml.safe_load((REPO / 'backend/charts' / chart).read_text())
        entries = {item['name']: item.get('value') for item in values['env']}
        assert entries[MODE_KEY] == 'shadow', chart


def test_registry_and_classification_declare_the_mode():
    registry = yaml.safe_load((REPO / 'config/feature-flags.yaml').read_text())
    rows = [row for row in registry['flags'] if row.get('key') == MODE_KEY]
    assert len(rows) == 1
    assert rows[0]['lifecycle'] == 'rollout' and rows[0]['fail'] == 'closed'
    assert rows[0]['surfaces'] == ['backend'] and rows[0]['decision'] == 'pending'
    classification = json.loads((REPO / 'config/deployment-setting-classification.json').read_text())
    assert MODE_KEY in classification['kinds']['config']


def test_jev_companion_fault_preserves_legacy_record_and_skips(seam, monkeypatch, caplog):
    monkeypatch.setenv(containment_module.MODE_ENV, 'shadow')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_JEV_SHADOW_UID_ALLOWLIST', UID)
    monkeypatch.setattr(shadow, 'submit_with_context', lambda _executor, fn, *args: fn(*args))
    pendant, laptop = complementary_rows()
    rows = {'pendant': pendant, 'laptop': laptop}
    monkeypatch.setattr(
        shadow.conversations_db, 'get_conversation_for_capture_check', lambda uid, cid: (rows[cid], 'fingerprint')
    )
    monkeypatch.setattr(shadow, '_cap', lambda *args: 'admitted')
    monkeypatch.setattr(shadow, 'measure_capture_containment', MagicMock(side_effect=RuntimeError('PRIVATE-SENTINEL')))

    class Answer:
        served_model = 'typesafe/jev-1.13'

        def noul(self, name):
            return 0.75

    monkeypatch.setattr(shadow, 'ask_jev', lambda *args, **kwargs: Answer())
    emitted = []
    monkeypatch.setattr(shadow, '_record', lambda record: emitted.append(record))
    skip = shadow.CAPTURE_JEV_SHADOW_SKIPS.labels('same_scene', 'error')
    before = skip._value.get()
    with caplog.at_level(logging.INFO):
        shadow.submit_same_scene(UID, 'pendant', 'laptop')
    assert emitted[-1]['outcome'] == 'success' and emitted[-1]['p'] == 0.75
    assert skip._value.get() == before
    assert all('PRIVATE-SENTINEL' not in r.message for r in caplog.records)


BASE_COMMIT = 'cd3326b3a58d88338fc6219eb767c36f581fc106'
FIXED_GROUP_ID = '00000000-0000-0000-0000-000000000000'


def _baseline_policy():
    source = subprocess.run(
        ['git', 'show', f'{BASE_COMMIT}:backend/utils/conversations/duplicate_capture.py'],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    name = 'duplicate_capture_baseline'
    module = ModuleType(name)
    module.__file__ = str(REPO / 'backend/utils/conversations/duplicate_capture.py')
    sys.modules[name] = module
    try:
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


def _run_capture_flow(module, rows, last_id, monkeypatch, caplog):
    store = StrictFirestore()
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(groups_db, 'get_firestore_client', lambda: store)

    def query(uid, *, status, finished_after, limit):
        found = [
            deepcopy(r)
            for p, r in store.rows.items()
            if p[:2] == ('users', uid) and r['status'] == status and r['finished_at'] >= finished_after
        ]
        return sorted(found, key=lambda r: r['finished_at'])[:limit]

    monkeypatch.setattr(conversations_db, 'get_conversations_finished_after', query)
    store.rows.update({path(key): deepcopy(value) for key, value in rows.items()})
    events = []
    monkeypatch.setattr(module, 'record_product_event', lambda event, **kw: events.append((event, kw.get('outcome'))))
    monkeypatch.setattr(module, 'submit_same_scene', lambda *args: None)
    monkeypatch.setattr(module, 'submit_resummary', lambda *args: None)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        module.link_duplicate_captures(UID, Conversation(**deepcopy(rows[last_id])))
    return store, events, [record.message for record in caplog.records]


def _snapshot(store):
    rows = json.dumps([[list(key), value] for key, value in sorted(store.rows.items())], sort_keys=True, default=str)
    updates = json.dumps(
        [[list(p), payload] for transaction in store.transactions for p, payload in transaction.updates],
        sort_keys=True,
        default=str,
    )
    return rows, updates


@pytest.mark.parametrize('fixture', ['separate', 'symmetric'])
def test_off_mode_is_identical_to_baseline(monkeypatch, caplog, fixture):
    baseline = _baseline_policy()
    monkeypatch.setenv(containment_module.MODE_ENV, 'off')
    monkeypatch.setattr(groups_db.uuid, 'uuid4', lambda: FIXED_GROUP_ID)
    original_record = groups_db._record

    def frozen_record(*args, **kwargs):
        record = original_record(*args, **kwargs)
        record['updated_at'] = T0
        return record

    monkeypatch.setattr(groups_db, '_record', frozen_record)
    if fixture == 'separate':
        pendant, laptop = complementary_rows()
        rows = {'pendant': pendant, 'laptop': laptop}
        last_id = 'laptop'
    else:
        legacy = [{'text': LEGACY_TEXT, 'speaker': 'SPEAKER_00', 'is_user': False, 'start': 0.0, 'end': 60.0}]
        rows = {
            'pendant': row('pendant', 'omi', 0, 600, legacy),
            'desktop': row('desktop', 'desktop', 100, 590, legacy),
        }
        last_id = 'desktop'
    baseline_state = _run_capture_flow(baseline, rows, last_id, monkeypatch, caplog)
    current_state = _run_capture_flow(policy, rows, last_id, monkeypatch, caplog)
    assert _snapshot(baseline_state[0]) == _snapshot(current_state[0])
    assert baseline_state[1] == current_state[1]
    assert baseline_state[2] == current_state[2]


def test_shared_speech_is_unchanged_from_baseline():
    baseline = subprocess.run(
        ['git', 'show', f'{BASE_COMMIT}:backend/utils/conversations/shared_speech.py'],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    assert baseline == (REPO / 'backend/utils/conversations/shared_speech.py').read_bytes()
