"""Verify cached community-1 bytes against canonical public revision metadata.

This read-only audit never grants repository access or substitutes a revision.
The canonical metadata must come from an unauthenticated files_metadata=True
model_info response for the exact serving revision. Download access is a separate
fact: a successful metadata proof does not imply authenticated download access.
"""

import argparse
import hashlib
import json
from pathlib import Path

import yaml

# Independently fixed audit target; the unit test fences serving-pin drift.
# Importing startup here would initialize NeMo and its verbose diagnostics.
DIARIZER_REVISION = '3533c8cf8e369892e6b79ff1bf80f7b0286a54ee'
MIRROR_REVISION = '8a527374977391da736e0daaef26855d949d9685'
MODEL_FILES = (
    'config.yaml',
    'embedding/pytorch_model.bin',
    'segmentation/pytorch_model.bin',
    'plda/plda.npz',
    'plda/xvec_transform.npz',
)


def audit(canonical, mirror_tree, snapshot):
    """Fail closed unless metadata and every referenced local model byte match."""
    if canonical.get('revision') != DIARIZER_REVISION:
        raise ValueError('canonical revision mismatch')
    rows = canonical['files']
    by_path = {row['path']: row for row in rows}
    if len(by_path) != len(rows) or set(by_path) != set(mirror_tree['files']):
        raise ValueError('repository file inventory mismatch')
    for path, row in by_path.items():
        mirror = mirror_tree['files'][path]
        lfs = row.get('lfs') or {}
        if (
            row['blob_id'] != mirror['blob_id']
            or row['size'] != mirror['size']
            or lfs.get('sha256') != mirror.get('lfs_sha256')
            or lfs.get('size') != mirror.get('lfs_size')
        ):
            raise ValueError('repository metadata mismatch')
    snapshot = Path(snapshot)
    if not set(MODEL_FILES).issubset(by_path):
        raise ValueError('model file inventory incomplete')
    for path in by_path:
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('unsafe repository path')
        row = by_path[path]
        data = (snapshot / path).read_bytes()
        if len(data) != row['size']:
            raise ValueError('local model size mismatch')
        lfs = row.get('lfs')
        if lfs:
            digest = hashlib.sha256(data).hexdigest()
            expected = lfs['sha256']
        else:
            digest = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
            expected = row['blob_id']
        if digest != expected:
            raise ValueError('local model digest mismatch')
    config = yaml.safe_load((snapshot / 'config.yaml').read_text())
    params = config['pipeline']['params']
    if {key: params.get(key) for key in ('segmentation', 'embedding', 'plda')} != {
        'segmentation': '$model/segmentation',
        'embedding': '$model/embedding',
        'plda': '$model/plda',
    }:
        raise ValueError('unverified model reference')
    return {
        'status': 'PASS',
        'canonical_revision': DIARIZER_REVISION,
        'mirror_revision': MIRROR_REVISION,
        'metadata_file_count': len(rows),
        'verified_file_count': len(rows),
        'verified_model_file_count': len(MODEL_FILES),
        'model_bytes_identical': True,
        'download_access_verified': False,
        'runtime_equivalence_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical-metadata', required=True, type=Path)
    parser.add_argument('--mirror-cache', required=True, type=Path, help='mirror repository cache directory')
    parser.add_argument(
        '--snapshot-dir', type=Path, help='complete read-only candidate snapshot, when cache is partial'
    )
    args = parser.parse_args()
    try:
        result = audit(
            json.loads(args.canonical_metadata.read_text()),
            json.loads((args.mirror_cache / 'trees' / f'{MIRROR_REVISION}.json').read_text()),
            args.snapshot_dir or args.mirror_cache / 'snapshots' / MIRROR_REVISION,
        )
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error_type': type(exc).__name__}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
