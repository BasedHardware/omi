"""User audio gets a SIGNED url; marketplace assets keep a public one (ADR-0087, BACKLOG L6).

Measured on the live RustFS: `public_url` was broken for all ten producers — the object ACL is not
honoured and the buckets carry no anonymous policy, so an anonymous GET is 403. The interesting part was
not the breakage but WHAT was behind those URLs. Five of the ten return an unauthenticated link for the
user's own audio: their enrolled voice, their conversation recordings, the file being synced. On GCS
those links work, because upstream's buckets are public by project policy.

So "make public_url work" would have created the exposure instead of closing it. The split:

    user audio          signed, time-limited   speech profile, post-processing, sd-card,
                                               conversation recording, syncing temporal file
    marketplace assets  public                 app logo, app thumbnail — public by definition
    chat files          UNDECIDED              the only producer that uploads with public=True; left
                                               exactly as found, and pinned here so the decision is
                                               made deliberately rather than by drift

The consumers were checked before changing anything, because a signed URL expires and a stored one
becomes a deferred 403: none of the five is persisted. Two have no caller at all, one has its return
value discarded, one is consumed immediately by the STT provider, and one is handed straight back to the
client in the upload response.
"""

from __future__ import annotations

import pytest

from tests.object_store_fakes import FakeObjectStore


class _RecordingStore(FakeObjectStore):
    """A fake that remembers which URL-minting method each producer reached for."""

    def __init__(self):
        super().__init__()
        self.signed: list[tuple[str, str, int]] = []
        self.public: list[tuple[str, str]] = []

    def presign_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        self.signed.append((bucket, key, expires_seconds))
        return f'https://signed.invalid/{bucket}/{key}?exp={expires_seconds}'

    def public_url(self, bucket: str, key: str) -> str:
        self.public.append((bucket, key))
        return f'https://public.invalid/{bucket}/{key}'


@pytest.fixture
def store(monkeypatch, tmp_path):
    from utils.other import storage

    fake = _RecordingStore()
    monkeypatch.setattr(storage, '_object_store', lambda: fake)
    # The signed-url helper caches by object key in Redis; bypass it so each test sees its own call.
    monkeypatch.setattr(storage, 'get_cached_signed_url', lambda key: None)
    monkeypatch.setattr(storage, 'cache_signed_url', lambda key, url, ttl: None)
    # The bucket name is read into a module-level constant at import, so the env var is too late.
    monkeypatch.setattr(storage, 'speech_profiles_bucket', 'speech-profiles', raising=False)
    return fake


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / 'a.wav'
    path.write_bytes(b'RIFF....WAVE')
    return str(path)


# --- user audio ------------------------------------------------------------------------------------


def test_the_enrolled_voice_gets_a_signed_url(store, audio_file):
    """The sharpest of the five: this is the user's voice, and the URL used to be unauthenticated."""
    from utils.other.storage import USER_AUDIO_URL_MINUTES, upload_profile_audio

    url = upload_profile_audio(audio_file, 'u1')

    assert store.public == [], 'a public URL for the enrolled voice is the defect, not the fix'
    assert store.signed == [('speech-profiles', 'u1/speech_profile.wav', USER_AUDIO_URL_MINUTES * 60)]
    assert url.startswith('https://signed.invalid/')


def test_the_post_processing_audio_gets_a_signed_url(store, audio_file):
    """Consumed by the STT provider, which fetches it once. The caller already called the result
    `signed_url` — this makes the name true."""
    from utils.other.storage import upload_postprocessing_audio

    upload_postprocessing_audio(audio_file)

    assert store.public == []
    assert len(store.signed) == 1 and store.signed[0][2] > 0


def test_the_conversation_recording_gets_a_signed_url(store, audio_file):
    from utils.other.storage import upload_conversation_recording

    upload_conversation_recording(audio_file, 'u1', 'c1')

    assert store.public == []
    assert store.signed[0][1] == 'u1/c1.wav'


def test_the_sdcard_audio_gets_a_signed_url(store, audio_file):
    from utils.other.storage import upload_sdcard_audio

    upload_sdcard_audio(audio_file)

    assert store.public == []
    assert store.signed[0][1].startswith('sdcard/')


def test_the_syncing_temporal_file_gets_a_signed_url(store, audio_file):
    """Its twin already minted a signed URL with a 15-minute expiry; this one carried the same audio
    behind a public link. Same content, same treatment."""
    from utils.other.storage import get_syncing_file_temporal_url

    get_syncing_file_temporal_url(audio_file)

    assert store.public == []
    assert len(store.signed) == 1


def test_every_signed_url_expires(store, audio_file):
    """A signed URL with no expiry would be a public URL with extra steps."""
    from utils.other.storage import upload_conversation_recording, upload_postprocessing_audio, upload_profile_audio

    upload_profile_audio(audio_file, 'u1')
    upload_postprocessing_audio(audio_file)
    upload_conversation_recording(audio_file, 'u1', 'c1')

    assert store.signed, 'precondition'
    assert all(expires > 0 for _bucket, _key, expires in store.signed)


# --- marketplace assets ------------------------------------------------------------------------------


def test_the_app_logo_keeps_a_public_url(store, tmp_path):
    """Public by definition. Signing it would make it non-cacheable and expiring, for content whose
    whole purpose is to be fetched by anyone."""
    from utils.other.storage import upload_app_logo

    logo = tmp_path / 'logo.png'
    logo.write_bytes(b'\x89PNG')

    upload_app_logo(str(logo), 'app-1')

    assert store.signed == [], 'a marketplace logo must not need a credential'
    assert len(store.public) == 1


def test_the_app_thumbnail_keeps_a_public_url(store, tmp_path):
    from utils.other.storage import upload_app_thumbnail

    thumbnail = tmp_path / 't.png'
    thumbnail.write_bytes(b'\x89PNG')

    upload_app_thumbnail(str(thumbnail), 'thumb-1')

    assert store.signed == []
    assert len(store.public) == 1


# --- chat attachments: decided, and decided differently ---------------------------------------------


def test_chat_thumbnails_store_a_key_rather_than_either_kind_of_url(store, tmp_path, monkeypatch):
    """This pin used to assert that chat files were LEFT AS FOUND, because the decision was open. It is
    taken now (ADR-0087) and it went a third way: the thumbnail is the user's content, so it must not be
    public — but its URL is PERSISTED in the message document, so a signed one would expire in place.
    The key is stored and the URL is minted at read time. Re-expressed rather than deleted, so the
    property it guards moves with the decision instead of disappearing with it; the read path has its
    own suite in test_chat_thumbnail_urls.py."""
    from utils.other import storage

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'thumb.png').write_bytes(b'\x89PNG')

    keys = storage.upload_multi_chat_files(['thumb.png'], 'u1')

    assert keys == {'thumb.png': 'u1/thumb.png'}
    assert store.public == [], 'no public URL: the thumbnail is the user\'s content'
    assert store.signed == [], 'and no signed one either at write time: it would expire in the document'
