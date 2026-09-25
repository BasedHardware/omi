"""The dev parity-pack bucket purge must delete only screen-derived cassettes.

`scripts/ensure_dev_parity_pack_bucket.py` runs from the dev listen deploy with
GCS credentials. Screen-surface capture is refused at write time now, but
cassettes exported before that gate still hold bounded window titles and OCR
text in `gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0/cassettes/`.
These tests pin the classifier and the gcloud command flow hermetically.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import scripts.ensure_dev_parity_pack_bucket as ensure_bucket


def _cassette(**extra: str) -> str:
    return json.dumps({"schema_version": 1, "events": [], **extra})


def test_classifier_matches_the_capture_gates_screen_rule() -> None:
    assert ensure_bucket.cassette_is_screen_derived(_cassette(surface="screen_activity_sync"))
    assert ensure_bucket.cassette_is_screen_derived(_cassette(surface="Screen"))
    assert ensure_bucket.cassette_is_screen_derived(_cassette(source="ocr_embed"))
    assert ensure_bucket.cassette_is_screen_derived(_cassette(surface="listen", source="OCRTEXT"))


def test_classifier_keeps_non_screen_and_unparseable_cassettes() -> None:
    assert not ensure_bucket.cassette_is_screen_derived(_cassette(surface="listen", source="stt"))
    assert not ensure_bucket.cassette_is_screen_derived(_cassette())
    assert not ensure_bucket.cassette_is_screen_derived("not json")
    assert not ensure_bucket.cassette_is_screen_derived(json.dumps(["list"]))


def test_purge_deletes_only_screen_cassettes(monkeypatch) -> None:
    objects = [
        "gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0/cassettes/a.json",
        "gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0/cassettes/b.json",
        "gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0/cassettes/c.json",
    ]
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, check: bool = True) -> SimpleNamespace:
        calls.append(args)
        if args[1:3] == ["storage", "ls"]:
            return SimpleNamespace(returncode=0, stdout="\n".join(objects) + "\n", stderr="")
        if args[1:3] == ["storage", "cat"]:
            body = (
                _cassette(surface="screen_activity_sync")
                if args[3].endswith(("a.json", "c.json"))
                else _cassette(surface="listen")
            )
            return SimpleNamespace(returncode=0, stdout=body, stderr="")
        if args[1:3] == ["storage", "rm"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected gcloud call: {args}")

    monkeypatch.setattr(ensure_bucket, "run", fake_run)

    removed = ensure_bucket.purge_screen_cassettes()

    assert removed == 2
    rm_targets = [args[3] for args in calls if args[1:3] == ["storage", "rm"]]
    assert rm_targets == [objects[0], objects[2]]


def test_purge_skips_cleanly_when_listing_fails(monkeypatch) -> None:
    def fake_run(args: list[str], *, check: bool = True) -> SimpleNamespace:
        assert args[1:3] == ["storage", "ls"]
        return SimpleNamespace(returncode=1, stdout="", stderr="bucket unreachable")

    monkeypatch.setattr(ensure_bucket, "run", fake_run)

    assert ensure_bucket.purge_screen_cassettes() == 0
