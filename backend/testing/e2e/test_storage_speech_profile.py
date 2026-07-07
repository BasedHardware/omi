"""Storage-backed speech-profile route coverage."""

from fakes.storage import FakeStorageClient, fake_blob_exists


def test_speech_profile_reads_fake_gcs_blob(client, auth_headers, test_uid):
    before = client.get("/v3/speech-profile", headers=auth_headers)
    assert before.status_code == 200, before.text
    assert before.json() == {"has_profile": False}

    blob = FakeStorageClient().bucket("speech-profiles").blob(f"{test_uid}/speech_profile.wav")
    blob.upload_from_string(b"fake-wav-bytes", content_type="audio/wav")

    has_profile = client.get("/v3/speech-profile", headers=auth_headers)
    assert has_profile.status_code == 200, has_profile.text
    assert has_profile.json() == {"has_profile": True}

    profile_url = client.get("/v4/speech-profile", headers=auth_headers)
    assert profile_url.status_code == 200, profile_url.text
    body = profile_url.json()
    assert body["url"].startswith("https://fake-gcs.local/speech-profiles/")
    assert body["url"].endswith("?signed=1")


def test_extra_speech_profile_samples_list_and_delete_fake_gcs(client, auth_headers, test_uid):
    bucket = FakeStorageClient().bucket("speech-profiles")
    bucket.blob(f"{test_uid}/additional_profile_recordings/mem1_segment_0.wav").upload_from_string(b"sample")

    listed = client.get("/v3/speech-profile/expand", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    urls = listed.json()
    assert len(urls) == 1
    assert "additional_profile_recordings/mem1_segment_0.wav" in urls[0]

    deleted = client.delete("/v3/speech-profile/expand?memory_id=mem1&segment_idx=0", headers=auth_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "ok"}
    assert not fake_blob_exists("speech-profiles", f"{test_uid}/additional_profile_recordings/mem1_segment_0.wav")
