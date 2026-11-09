"""Late WAL is in the partial inventory, even with an already retained tail."""

from utils.batch_pipeline import record_lease_append as append
from tests.unit.test_record_gap_fill import (
    world,
    UID,
    CID,
    closed_row,
    tone,
    audio_unit,
    materialized,
)
from database.audio_timeline import span_blob_metadata


def test_partial_wal_retains_interior_holes_create_only(world, monkeypatch):
    world.bucket.put(
        f'chunks/{UID}/{CID}/100.000000.bin',
        tone(1, 1),
        span_blob_metadata({'start': 100, 'samples': 16000, 'sample_rate': 16000}),
    )
    world.bucket.put(
        f'chunks/{UID}/{CID}/109.000000.bin',
        tone(1, 9),
        span_blob_metadata({'start': 109, 'samples': 16000, 'sample_rate': 16000}),
    )
    original = {key: dict(value) for key, value in world.bucket.objects.items()}
    world.wal['units'] = [audio_unit(105, tone(1, 5)), audio_unit(105.5, tone(1, 6))]
    monkeypatch.setattr(append.gap, 'create_storage_client', lambda: object())
    monkeypatch.setattr(append, 'list_audio_chunks', lambda *a, **kw: world.bucket.listing())
    monkeypatch.setattr(append.gap, 'gap_fill_bucket', lambda *a: world.bucket)
    row = closed_row(data_protection_level='standard', record_audio_closed=False, record_audio_partial={'version': 1})
    append.retain(UID, CID, row, ['synthetic'])
    for key, value in original.items():
        assert world.bucket.objects[key] == value
    assert world.bucket.objects[f'chunks/{UID}/{CID}/105.000000.bin']['data'] == tone(1, 5)
    assert f'chunks/{UID}/{CID}/105.500000.bin' not in world.bucket.objects
    assert world.bucket.objects[f'chunks/{UID}/{CID}/106.000000.bin']['data'] == tone(0.5, 6)
    objects = {key: dict(value) for key, value in world.bucket.objects.items()}
    append.retain(UID, CID, row, ['synthetic'])
    assert world.bucket.objects == objects  # exact retry neither overwrites nor adds audio
    units = list(
        append.retained_record_units(
            UID, CID, world.bucket.listing(), None, append.encryption.derive_key(UID), partial=True
        )
    )
    containing = next(unit for unit in units if unit[0] <= 105 < unit[0] + unit[1])
    pcm = materialized(world, containing)
    first = round((105 - containing[0]) * 16000) * 2
    assert pcm[first : first + 32000] == tone(1, 5)
