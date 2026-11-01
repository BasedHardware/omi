"""David-only staging mirror: owner pin, layout classification, copy (swarm lane 4)."""

import hashlib
import json
import os
import struct

import pytest

from scripts.staging import mirror_owner_recordings as mo
from testing.loadgen import mirror_codec as mc
from utils import encryption

UID = 'ownerUidForMirrorTests0001'
STAGING_SECRET = 'z' * 48


def test_owner_pin_requires_literal_singletons():
    env = {
        'BATCH_PIPELINE_UID_ALLOWLIST': UID,
        'DREAM_AGENT_UID_ALLOWLIST': f' {UID} ',
        'TRANSCRIPTION_SHADOW_UID_ALLOWLIST': UID,
    }
    mo.verify_owner_pin(UID, env)
    for broken in (
        {**env, 'DREAM_AGENT_UID_ALLOWLIST': None},  # secret ref
        {'BATCH_PIPELINE_UID_ALLOWLIST': UID, 'DREAM_AGENT_UID_ALLOWLIST': UID},  # missing
        {**env, 'BATCH_PIPELINE_UID_ALLOWLIST': f'{UID},someoneElse'},
        {**env, 'BATCH_PIPELINE_UID_ALLOWLIST': 'someoneElse'},
    ):
        with pytest.raises(mo.MirrorRefused):
            mo.verify_owner_pin(UID, broken)
    with pytest.raises(mo.MirrorRefused):
        mo.verify_owner_pin('', env)


def test_cloud_run_env_treats_secret_refs_as_absent():
    class Session:
        def get(self, url, timeout):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        'template': {
                            'containers': [
                                {
                                    'env': [
                                        {'name': 'A', 'value': 'x'},
                                        {'name': 'B', 'valueSource': {'secretKeyRef': {'secret': 's'}}},
                                    ]
                                }
                            ]
                        }
                    }

            assert '/services/backend-sync' in url
            return R()

    assert mo.cloud_run_literal_env(Session(), 'p', 'backend-sync') == {'A': 'x', 'B': None}


@pytest.mark.parametrize(
    'source,name,meta,expect',
    [
        (
            'private-cloud-sync',
            f'chunks/{UID}/conv1/1760000000.123.opus.enc',
            None,
            ('chunk', mc.FORMAT_CHUNK_OPUS, True),
        ),
        ('private-cloud-sync', f'chunks/{UID}/conv1/1760000000.123.opus', None, ('chunk', mc.FORMAT_CHUNK_OPUS, False)),
        ('private-cloud-sync', f'chunks/{UID}/conv1/1760000000.123.enc', None, ('chunk', mc.FORMAT_CHUNK_PCM16, True)),
        ('private-cloud-sync', f'chunks/{UID}/conv1/1760000000.bin', None, ('chunk', mc.FORMAT_CHUNK_PCM16, False)),
        (
            'private-cloud-sync',
            f'raw-sync/{UID}/audio_omi_opus_16000_1_fs160_1760000000.bin/abc.bin.enc',
            {'conversation_ids': '["c9"]', 'sha256': 'f' * 64},
            ('raw-sync', mc.FORMAT_RAW_UPLOAD, True),
        ),
        (
            'private-cloud-sync',
            f'chunks/{UID}/conv1/1760000000.100-1760000009.900.batch.enc',
            {'v2_sample_rate': '16000'},
            ('chunk', mc.FORMAT_CHUNK_PCM16, True),
        ),
        (
            'syncing-local',
            f'syncing/{UID}/job1/audio_abcdef0123456789_opus_fs320_16000_1_fs320_1760000000.123.bin',
            None,
            ('syncing', mc.FORMAT_RAW_UPLOAD, False),
        ),
        (
            'syncing-local',
            f'syncing/{UID}/job1/audio_omi_pcm16_16000_1_fs160_1760000000.bin',
            None,
            ('syncing', mc.FORMAT_RAW_UPLOAD, False),
        ),
    ],
)
def test_classify_known_layouts(source, name, meta, expect):
    got = mo.classify(source, UID, name, 1000, meta)
    assert isinstance(got, mo.SourceObject)
    assert (got.kind, got.source_format, got.encrypted) == expect


def test_classify_skips_foreign_and_unsupported():
    assert (
        mo.classify('private-cloud-sync', UID, f'chunks/{UID}/c/1.batch.enc', 10, {'v2_sample_rate': '8000'})
        == 'non_16k_pcm'
    )
    assert mo.classify('private-cloud-sync', UID, 'chunks/other/c/1.opus', 10, None) == 'unrecognized_layout'
    assert (
        mo.classify('private-cloud-sync', UID, f'raw-sync/other/audio_omi_opus_16000_1_fs160_1.bin/x.bin', 10, None)
        == 'foreign_owner'
    )
    assert mo.classify('syncing-local', UID, f'syncing/{UID}/job/1760000000.wav', 10, None) == 'syncing_not_upload_file'
    assert mo.classify('syncing-local', UID, f'syncing/{UID}/job/x.bin', 0, None) == 'size_out_of_bounds'


def test_read_only_bucket_allowlist():
    class Client:
        def bucket(self, name):
            return name

    with pytest.raises(mo.MirrorRefused):
        mo.ReadOnlyBucket(Client(), 'based-hardware-batch-pipeline-staging')
    assert mo.ReadOnlyBucket(Client(), 'syncing-local').name == 'syncing-local'
    assert not hasattr(mo.ReadOnlyBucket, 'put') and not hasattr(mo.ReadOnlyBucket, 'delete')


def _inventory():
    inv = mo.Inventory()
    for conv, base in (('grpOLDx', 1_700_000_000.0), ('grpNEWx', 1_760_000_000.0), ('grpMIDx', 1_730_000_000.0)):
        for i in range(3):
            got = mo.classify('private-cloud-sync', UID, f'chunks/{UID}/{conv}/{base + i * 10:.3f}.opus.enc', 500, None)
            inv.objects.append(got)
    inv.listed = {'chunks': 9}
    inv.skipped = {'batch_container_unsupported': 1}
    return inv


def test_select_newest_groups_and_record_has_no_identifiers():
    inv = _inventory()
    selected = mo.select_groups(inv, max_groups=2)
    assert [files[0].group for files in selected] == ['grpNEWx', 'grpMIDx']
    assert mo.select_groups(inv, max_groups=5, since=1_750_000_000.0)[0][0].group == 'grpNEWx'
    record = mo.inventory_record(inv, selected)
    text = json.dumps(record)
    assert UID not in text and 'grp' not in text and 'chunks/' not in text
    assert record['recordings']['chunk_conversations'] == 3
    assert record['selected']['objects'] == 6
    assert record['mirrorable_by_kind']['chunk/chunk-opus-lp']['encrypted'] == 9


def _opus_container(n):
    packets = [bytes([7]) * 20] * n
    return struct.pack('<II', n, n * 640) + b''.join(struct.pack('<H', len(p)) + p for p in packets)


def test_copy_object_decrypts_reseals_and_records_hashes():
    plain = _opus_container(50)
    obj = mo.classify('private-cloud-sync', UID, f'chunks/{UID}/c1/1760000000.000.opus.enc', 900, None)
    written = {}
    stats = mo.CopyStats()
    mirror_key = mc.derive_mirror_key(STAGING_SECRET)
    entry = mo.copy_object(
        obj,
        0,
        owner_label='owner-a',
        group='g' * 32,
        read=lambda o: encryption.encrypt_audio_chunk(plain, UID),
        prod_user_key=lambda: mc.derive_prod_user_key(os.environ['ENCRYPTION_SECRET'], UID),
        mirror_key=mirror_key,
        write=lambda name, sealed, meta: written.setdefault(name, (sealed, meta)) is not None,
        stats=stats,
    )
    assert entry and abs(entry['duration_s'] - 1.0) < 1e-6  # not pytest.approx: it imports numpy in the timed call
    sealed, meta = written[entry['object']]
    assert mc.open_mirror_object(mirror_key, entry['object'], sealed) == plain
    assert meta['plaintext_sha256'] == hashlib.sha256(plain).hexdigest() == entry['plaintext_sha256']
    assert plain not in sealed and UID not in entry['object']
    assert stats.decrypted == 1 and stats.read_objects == 1 and not stats.failed


def test_copy_object_rejects_sha_mismatch_and_bad_audio():
    body = mc.wal_frame([b'\x00\x01' * 800] * 4)
    name = f'raw-sync/{UID}/audio_omi_pcm16_16000_1_fs160_1760000000.bin/x.bin'
    obj = mo.classify('private-cloud-sync', UID, name, len(body), {'sha256': '0' * 64})
    stats = mo.CopyStats()
    kwargs = dict(
        owner_label='owner-a',
        group='g',
        prod_user_key=lambda: b'',
        mirror_key=mc.derive_mirror_key(STAGING_SECRET),
        write=lambda *a: True,
        stats=stats,
    )
    assert mo.copy_object(obj, 0, read=lambda o: body, **kwargs) is None
    assert stats.failed == {'sha256_mismatch': 1}
    chunk = mo.classify('private-cloud-sync', UID, f'chunks/{UID}/c/1760000000.000.opus', 10, None)
    assert mo.copy_object(chunk, 0, read=lambda o: b'\x01\x02', **kwargs) is None
    assert stats.failed['unparseable_audio'] == 1


def test_writer_only_targets_the_mirror_bucket():
    with pytest.raises(mo.MirrorRefused):
        mo.make_writer(object(), 'based-hardware-dev-staging-sync')


def test_copy_stats_public_is_serializable():
    stats = mo.CopyStats()
    stats.audio_seconds = 7200.0
    stats.fail('read:Timeout')
    out = stats.public()
    assert out['audio_hours'] == 2.0 and out['failed'] == {'read:Timeout': 1}
    json.dumps(out)


def test_private_cloud_sync_reads_only_the_owner_chunk_prefix():
    assert mo.prefixes_for('private-cloud-sync', UID) == [f'chunks/{UID}/']


def test_spread_selection_covers_history_and_size_bound():
    inv = mo.Inventory()
    for n in range(10):
        got = mo.classify(
            'private-cloud-sync',
            UID,
            f'chunks/{UID}/grp{n:02d}x/{1_700_000_000 + n * 86400:.3f}.opus.enc',
            500 if n != 9 else 5_000_000,
            None,
        )
        inv.objects.append(got)
    picked = mo.select_groups(inv, max_groups=3, spread=True, max_group_bytes=1_000_000)
    assert [f[0].group for f in picked] == ['grp08x', 'grp05x', 'grp02x']
    assert [f[0].group for f in mo.select_groups(inv, max_groups=2)] == ['grp09x', 'grp08x']
