"""Revision proof must include actual model and non-model bytes."""

import hashlib
import pytest

from scripts.diarization_eval import revision_audit as module
from diarizer.batch_pipeline_startup import DIARIZER_REVISION


def test_audit_target_matches_serving_pin():
    assert module.DIARIZER_REVISION == DIARIZER_REVISION


def fixture(tmp_path):
    config = b'pipeline:\n  params:\n    segmentation: $model/segmentation\n    embedding: $model/embedding\n    plda: $model/plda\n'
    rows, mirror = [], {}
    for path in (*module.MODEL_FILES, 'README.md'):
        data = config if path == 'config.yaml' else b'synthetic public model asset'
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        lfs = (
            None if path.endswith(('.yaml', '.md')) else {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        )
        rows.append({'path': path, 'blob_id': blob, 'size': len(data), 'lfs': lfs})
        mirror[path] = {'blob_id': blob, 'size': len(data)}
        if lfs:
            mirror[path].update(lfs_sha256=lfs['sha256'], lfs_size=lfs['size'])
    return {'revision': module.DIARIZER_REVISION, 'files': rows}, {'files': mirror}


def test_exact_metadata_and_all_bytes_prove_integrity_without_access_claim(tmp_path):
    canonical, mirror = fixture(tmp_path)
    result = module.audit(canonical, mirror, tmp_path)
    assert result['model_bytes_identical']
    assert result['verified_file_count'] == 6
    assert not result['download_access_verified']
    assert not result['runtime_equivalence_verified']


@pytest.mark.parametrize('path', ['embedding/pytorch_model.bin', 'README.md'])
def test_metadata_match_cannot_hide_corrupt_actual_bytes(tmp_path, path):
    canonical, mirror = fixture(tmp_path)
    data = (tmp_path / path).read_bytes()
    (tmp_path / path).write_bytes(b'x' * len(data))
    with pytest.raises(ValueError, match='digest mismatch'):
        module.audit(canonical, mirror, tmp_path)


def test_different_canonical_metadata_is_not_equivalence(tmp_path):
    canonical, mirror = fixture(tmp_path)
    canonical['files'][0]['blob_id'] = '0' * 40
    with pytest.raises(ValueError, match='metadata mismatch'):
        module.audit(canonical, mirror, tmp_path)


def test_missing_actual_file_cannot_pass(tmp_path):
    canonical, mirror = fixture(tmp_path)
    (tmp_path / 'README.md').unlink()
    with pytest.raises(FileNotFoundError):
        module.audit(canonical, mirror, tmp_path)
