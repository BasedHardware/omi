"""Loopback-only native UI fixture using the production routes and assignment transaction.

Run: OMI_ENV_STAGE=offline backend/.venv/bin/python -m testing.e2e.owner_confirmation_fixture
from backend/. Audio is synthesized locally; no credentials, cloud data or providers.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI

from database import conversations as db
from routers import speaker_tag_prompts as routes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.speaker_tag_prompts import service

UID = 'synthetic-owner'
CID = 'synthetic-conversation'
STORE = StrictFirestore()
PATH = ('users', UID, 'conversations', CID)
STATE = {}
CACHE = {}
PCM = b''


def decoded():
    raw = deepcopy(STORE.rows[PATH])
    raw['transcript_segments'] = db._decode_transcript_segments_strict(
        UID, raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
    )
    raw['manual_speaker_assignments'] = db.decode_manual_speaker_assignments(
        UID, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    return raw


def reset(owner: bool = False):
    STATE.clear()
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    STORE.rows.clear()
    STORE.rows[('users', UID)] = {'speaker_embedding': [1.0, 0.0]}
    STORE.rows[PATH] = dict(
        id=CID,
        status='completed',
        started_at=started,
        created_at=started,
        discarded=False,
        structured={'title': 'Synthetic coffee chat'},
        audio_files=[{'chunk_timestamps': [started.timestamp()], 'duration': 60.0}],
        transcript_segments=[
            dict(
                id='played',
                text='We should ship it on Friday.',
                speaker_id=1,
                speaker_id_scope='synthetic-capture',
                start=0.0,
                end=6.0,
                is_user=owner,
                person_id=None,
            ),
            dict(
                id='sibling',
                text='Unplayed sibling stays You.' if owner else 'Unplayed sibling stays Speaker 1.',
                speaker_id=1,
                speaker_id_scope='synthetic-capture',
                start=10.0,
                end=16.0,
                is_user=owner,
                person_id=None,
            ),
            dict(
                id='automatic',
                text='Unplayed automatic owner stays You.',
                speaker_id=2,
                speaker_id_scope='synthetic-capture',
                start=20.0,
                end=26.0,
                is_user=True,
                person_id=None,
            ),
        ],
    )
    return {'status': 'reset'}


def shown(uid, now):
    STATE['last_shown_at'] = now
    return False


def install_fixtures():
    # Storage and model boundaries are synthetic; the HTTP, selection, binding,
    # clip delivery, manual receipt and effects code are the production path.
    db.get_firestore_client = lambda: STORE
    db.get_conversation = lambda uid, cid: decoded()
    db.get_conversations = lambda *a, **k: [decoded()]
    db.invalidate_people_stats_cache = lambda uid: None
    db.record_speaker_review = lambda *a: None
    service.voice_profiles_db.get_voice_profile_context = lambda uid: (
        {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': False},
        True,
    )
    service.voice_profiles_db.get_tag_prompt_state = lambda uid: dict(STATE)
    service.voice_profiles_db.mark_tag_prompts_empty = lambda uid, now: STATE.update(last_empty_check_at=now)
    service.voice_profiles_db.record_tag_prompts_shown = shown
    service.voice_profiles_db.record_tag_prompt_answered = lambda *a: None
    service.users_db.get_user_speaker_embedding = lambda uid: [1.0, 0.0]
    service.named_speaker_prompts_allowed = lambda uid: False
    service.verified_clip_pcm = lambda *a, **k: PCM
    routes.conversation_clip_pcm = lambda *a, **k: PCM
    service.extract_embedding_from_bytes = lambda *a, **k: np.array([[0.5, 0.8660254]])
    service.redis_db.get_generic_cache = lambda key: CACHE.get(key)
    service.redis_db.set_generic_cache = lambda key, value, ttl: CACHE.__setitem__(key, value)
    service.emit_product_event = lambda **k: None


APP = FastAPI()
APP.include_router(routes.router)
for route in APP.routes:
    if hasattr(route, 'dependant'):
        for dep in route.dependant.dependencies:
            APP.dependency_overrides[dep.call] = lambda: UID


@APP.get('/fixture/transcript')
def transcript():
    return decoded()['transcript_segments']


@APP.post('/fixture/reset')
def fixture_reset(owner: bool = False):
    return reset(owner)


@APP.get('/fixture/receipt')
def receipt():
    raw = decoded()
    return {
        'receipt': raw.get('manual_speaker_assignments'),
        'prompt': raw.get('owner_confirmation_prompt'),
        'user': STORE.rows[('users', UID)],
    }


def main():
    global PCM
    parser = argparse.ArgumentParser()
    parser.add_argument('--pcm', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18955)
    args = parser.parse_args()
    PCM = args.pcm.read_bytes()
    if len(PCM) != 16000 * 6 * 2:
        raise ValueError('Fixture audio must be exactly six seconds of 16kHz mono PCM16')
    reset()
    install_fixtures()
    uvicorn.run(APP, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
