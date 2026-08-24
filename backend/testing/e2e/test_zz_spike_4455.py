"""SPIKE #4455 — riproduzione live, tier non-CI. Salta senza corpus o senza parakeet.

Due versanti della stessa storia utente («tagghi una voce, alla conversazione dopo è di nuovo
Speaker 1»):

  test_extraction_gates   quale delle nove uscite silenziose di ``extract_speaker_samples``
                          scatta con audio reale e uno STT vivo.
  test_next_conversation  chi viene caricato nella conversazione successiva, eseguendo il vero
                          ``SpeakerMatcher.load_and_run`` invece di ripeterne il predicato.
  test_recognised_in_conversation_two
                          il ciclo intero: taggo in conversazione 1, la persona deve essere
                          riconosciuta in conversazione 2. Serve anche il diarizer
                          (``HOSTED_SPEAKER_EMBEDDING_API_URL``).

Esecuzione (parakeet dal compose committato, ``--profile inference``). Il conftest E2E sostituisce
``socket.connect`` e ammette **solo indirizzi locali**, quindi si condivide il netns di parakeet
invece di usare la rete compose::

    docker run --rm --network container:omi-oss-parakeet-1 \\
      -v $(git rev-parse --show-toplevel):/repo -v ~/.cache/omi-oss/librispeech:/corpus:ro \\
      -w /repo/backend -e LOCAL_DEVELOPMENT=true -e OPENAI_API_KEY=test \\
      -e ENCRYPTION_SECRET="$(openssl rand -hex 32)" \\
      -e STT_PRERECORDED_MODEL=parakeet -e HOSTED_PARAKEET_API_URL=http://127.0.0.1:8080 \\
      omi-oss-backend-test /opt/venv/bin/python -m pytest -o addopts="" -s \\
      testing/e2e/test_zz_spike_4455.py
"""

import asyncio
import glob
import os
import wave
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

CORPUS = '/corpus'
SPEAKER_A = f'{CORPUS}/1221-135767-0000.wav'  # 24.9 s
SPEAKER_B = f'{CORPUS}/1320-122612-0000.wav'  # 13.5 s
RATE = 16000
CHUNK_SECONDS = 5.0

pytestmark = pytest.mark.skipif(
    not os.path.exists(SPEAKER_A) or not os.environ.get('HOSTED_PARAKEET_API_URL'),
    reason='live tier: needs the LibriSpeech corpus at /corpus and a reachable parakeet',
)


def _pcm(path):
    with wave.open(path) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2), path
        return w.readframes(w.getnframes())


def _transcript(name):
    """Ground truth from LibriSpeech, so containment is measured on a fair comparison."""
    for path in glob.glob(f'{CORPUS}/**/*.trans.txt', recursive=True):
        for line in open(path):
            if line.startswith(name + ' '):
                return line.split(' ', 1)[1].strip().lower()
    return ''


def test_extraction_gates(client, fake_storage, fake_firestore, test_uid, capsys):
    import database.conversations as conversations_db
    import database.users as users_db
    import utils.speaker_identification as si
    from utils.other.storage import upload_audio_chunk

    uid, person_id, conv_id = test_uid, 'person-spike', 'conv-spike'
    users_db.create_person(uid, {'id': person_id, 'name': 'Spike'})
    a, b = _pcm(SPEAKER_A), _pcm(SPEAKER_B)
    dur_a = len(a) / (RATE * 2)
    audio = a + b
    started = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    t0 = started.timestamp()

    stride = int(RATE * 2 * CHUNK_SECONDS)
    timestamps = []
    for i in range(0, len(audio), stride):
        ts = t0 + (i / (RATE * 2))
        upload_audio_chunk(audio[i : i + stride], uid, conv_id, ts)
        timestamps.append(ts)

    segments = [
        {
            'id': 'seg-a',
            'text': _transcript('1221-135767-0000'),
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
            'start': 0.0,
            'end': dur_a,
        },
        {
            'id': 'seg-b',
            'text': _transcript('1320-122612-0000'),
            'speaker': 'SPEAKER_01',
            'speaker_id': 1,
            'is_user': False,
            'start': dur_a + 0.1,
            'end': dur_a + 13.4,
        },
    ]
    conversations_db.upsert_conversation_with_lifecycle(
        uid,
        {
            'id': conv_id,
            'created_at': started,
            'started_at': started,
            'finished_at': started,
            'source': 'omi',
            'language': 'en',
            'status': 'completed',
            'discarded': False,
            'transcript_segments': segments,
            'audio_files': [{'chunk_timestamps': timestamps}],
            'structured': {'title': 'spike', 'overview': '', 'emoji': '🧪', 'category': 'other'},
        },
    )

    seen = []
    for level in ('info', 'warning', 'error'):
        setattr(si.logger, level, lambda m, *a, _l=level, **k: seen.append(f'{_l.upper()}: {m}'))

    asyncio.get_event_loop().run_until_complete(
        si.extract_speaker_samples(uid=uid, person_id=person_id, conversation_id=conv_id, segment_ids=['seg-a'])
    )

    samples = users_db.get_person_speech_samples_count(uid, person_id)
    with capsys.disabled():
        print('\n──── SPIKE #4455 · estrazione ────')
        print(f'parlante A {dur_a:.1f}s · {len(timestamps)} chunk seminati')
        for line in seen:
            print(f'  {line}')
        print(f'campioni memorizzati: {samples}')


def test_next_conversation(client, fake_storage, fake_firestore, fresh_uid, capsys):
    """Chi entra fra gli embedding della sessione successiva — eseguendo il vero loader."""
    import database.users as users_db
    from routers.listen.speakers import SpeakerMatcher

    uid = fresh_uid
    users_db.create_person(
        uid,
        {
            'id': 'verified',
            'name': 'Verified',
            'speech_samples': ['p.wav'],
            'speech_samples_version': 3,
            'speaker_embedding': [0.1] * 192,
        },
    )
    users_db.create_person(
        uid,
        {
            'id': 'unverified',
            'name': 'Unverified',
            'speech_samples': ['p.wav'],
            'speech_samples_version': 1,
            'speaker_embedding': [0.2] * 192,
        },
    )
    users_db.create_person(uid, {'id': 'nosample', 'name': 'NoSample', 'speaker_embedding': [0.3] * 192})

    async def _call(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=uid),
        persistence=SimpleNamespace(call=_call),
        has_speech_profile=False,
        state=SimpleNamespace(speaker_id_enabled=True, speaker_id_done=asyncio.Event(), active=False),
    )
    matcher = SpeakerMatcher(host)
    asyncio.get_event_loop().run_until_complete(matcher.load_and_run())

    loaded = sorted(matcher.person_embeddings)
    with capsys.disabled():
        print('\n──── SPIKE #4455 · conversazione successiva ────')
        print('  create   : verified(v3) · unverified(v1) · nosample(nessun campione)')
        print(f'  caricate : {loaded or "NESSUNA"}')


def test_recognised_in_conversation_two(client, fake_storage, fake_firestore, fresh_uid, capsys):
    """Il ciclo completo dell'utente: taggata in conversazione 1, riconosciuta in conversazione 2.

    Il corpus ha UNA frase per parlante, quindi i 24,9 s del parlante 1221 sono divisi a metà:
    la prima metà è la conversazione 1 (da cui si estrae il campione), la seconda è la
    conversazione 2 (su cui si chiede il riconoscimento). Stessa voce, parole diverse, entrambe
    sopra il minimo di 8 s che l'estrazione richiede.
    """
    if not os.environ.get('HOSTED_SPEAKER_EMBEDDING_API_URL'):
        pytest.skip('needs the diarizer for speaker embeddings')

    import database.conversations as conversations_db
    import database.users as users_db
    import utils.speaker_identification as si
    from routers.listen.speakers import SpeakerMatcher
    from utils.audio import AudioRingBuffer
    from utils.other.storage import upload_audio_chunk

    uid, person_id = fresh_uid, 'carol'
    full = _pcm(SPEAKER_A)
    half = (len(full) // 2) - ((len(full) // 2) % 2)
    first, second = full[:half], full[half:]
    dur_first = len(first) / (RATE * 2)
    text = _transcript('1221-135767-0000')

    users_db.create_person(uid, {'id': person_id, 'name': 'Carol'})

    # ── conversazione 1: tag manuale -> estrazione del campione ────────────────────────────
    conv1, started = 'conv-one', datetime(2026, 8, 24, 9, 0, 0, tzinfo=timezone.utc)
    t0 = started.timestamp()
    stride = int(RATE * 2 * CHUNK_SECONDS)
    stamps = []
    for i in range(0, len(first), stride):
        ts = t0 + (i / (RATE * 2))
        upload_audio_chunk(first[i : i + stride], uid, conv1, ts)
        stamps.append(ts)
    conversations_db.upsert_conversation_with_lifecycle(
        uid,
        {
            'id': conv1,
            'created_at': started,
            'started_at': started,
            'finished_at': started,
            'source': 'omi',
            'language': 'en',
            'status': 'completed',
            'discarded': False,
            'transcript_segments': [
                {
                    'id': 'c1-seg',
                    'text': ' '.join(text.split()[: len(text.split()) // 2]),
                    'speaker': 'SPEAKER_00',
                    'speaker_id': 0,
                    'is_user': False,
                    'start': 0.0,
                    'end': dur_first,
                }
            ],
            'audio_files': [{'chunk_timestamps': stamps}],
            'structured': {'title': 'one', 'overview': '', 'emoji': '1️⃣', 'category': 'other'},
        },
    )
    asyncio.get_event_loop().run_until_complete(
        si.extract_speaker_samples(uid=uid, person_id=person_id, conversation_id=conv1, segment_ids=['c1-seg'])
    )
    person = users_db.get_person(uid, person_id) or {}
    stored_samples = users_db.get_person_speech_samples_count(uid, person_id)

    # ── conversazione 2: la sessione carica le persone e chiede un match ───────────────────
    t1 = datetime(2026, 8, 24, 18, 0, 0, tzinfo=timezone.utc).timestamp()
    ring = AudioRingBuffer(duration_seconds=60.0, sample_rate=RATE)
    ring.write(second, t1 + len(second) / (RATE * 2))

    suggestions = []

    async def _call(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=uid, sample_rate=RATE),
        persistence=SimpleNamespace(call=_call),
        has_speech_profile=False,
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        state=SimpleNamespace(
            speaker_id_enabled=True,
            speaker_id_done=asyncio.Event(),
            active=False,
            audio_ring_buffer=ring,
            speaker_map_dirty=False,
        ),
        emit_speaker_suggestion=lambda *a: suggestions.append(a),
    )
    matcher = SpeakerMatcher(host)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(matcher.load_and_run())
    loaded = sorted(matcher.person_embeddings)
    loop.run_until_complete(
        matcher.match(
            0,
            {
                'id': 'c2-seg',
                'duration': len(second) / (RATE * 2),
                'abs_start': t1,
                'abs_end': t1 + len(second) / (RATE * 2),
            },
        )
    )

    with capsys.disabled():
        print('\n──── SPIKE #4455 · ciclo completo su due conversazioni ────')
        print(
            f'  conv 1: {dur_first:.1f}s -> campioni={stored_samples} '
            f'version={person.get("speech_samples_version")} embedding={"si" if person.get("speaker_embedding") else "NO"}'
        )
        print(f'  conv 2: persone caricate={loaded or "NESSUNA"}')
        print(f'          match      ={matcher.speaker_to_person or "NESSUNO"}')
        print(f'          suggerito  ={suggestions or "niente"}')
