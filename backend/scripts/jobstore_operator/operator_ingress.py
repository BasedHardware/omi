"""Source-only proposal: fixed same-repository draft assets, never arbitrary URLs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPOSITORY = 'BasedHardware/omi'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_release(contract, release):
    if (
        contract['repository'] != REPOSITORY
        or not isinstance(contract.get('release_id'), int)
        or contract['release_id'] <= 0
    ):
        raise ValueError('REVIEWED_RELEASE_ID_REQUIRED')
    if (
        release.get('id') != contract['release_id']
        or release.get('draft') is not True
        or release.get('published_at') is not None
    ):
        raise ValueError('EXACT_UNPUBLISHED_DRAFT_REQUIRED')
    if release.get('tag_name') != contract['release_tag'] or release.get('target_commitish') != contract['source_sha']:
        raise ValueError('DRAFT_SOURCE_BINDING_CHANGED')
    expected = contract['parts'] + [contract['fixture']]
    assets = release.get('assets', [])
    if len(assets) != len(expected) or len({a['name'] for a in assets}) != len(assets):
        raise ValueError('EXACT_ASSET_SET_REQUIRED')
    by_name = {a['name']: a for a in assets}
    for row in expected:
        if (
            not re.fullmatch(r'[a-zA-Z0-9._-]+', row['name'])
            or not isinstance(row.get('asset_id'), int)
            or row['asset_id'] <= 0
        ):
            raise ValueError('PINNED_ASSET_ID_REQUIRED')
        actual = by_name.get(row['name'], {})
        if (
            actual.get('id') != row['asset_id']
            or actual.get('size') != row['bytes']
            or actual.get('state') != 'uploaded'
            or actual.get('digest') != 'sha256:' + row['sha256']
        ):
            raise ValueError('ASSET_METADATA_CHANGED')
    return expected


def verify_and_assemble(contract, directory):
    for row in contract['parts'] + [contract['fixture']]:
        path = directory / row['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('ASSET_BYTES_CHANGED')
    output = directory / 'operator.oci.tar'
    hasher = hashlib.sha256()
    size = 0
    with output.open('xb') as target:
        for row in contract['parts']:
            with (directory / row['name']).open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    hasher.update(chunk)
                    size += len(chunk)
    if size != contract['archive_bytes'] or hasher.hexdigest() != contract['archive_sha256']:
        raise ValueError('COMBINED_ARCHIVE_CHANGED')
    return output


def run(argv, **kwargs):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900, **kwargs)
    if result.returncode:
        raise RuntimeError('COMMAND_FAILED_NO_CREDENTIAL_OR_RESPONSE_BODY_LOGGED')
    return result.stdout


def release_metadata(release_id):
    if not isinstance(release_id, int) or release_id <= 0:
        raise ValueError('NUMERIC_RELEASE_ID_REQUIRED')
    return json.loads(run(['gh', 'api', f'repos/{REPOSITORY}/releases/{release_id}']))


def stable_release_identity(release):
    # Counters, timestamps, presentation and uploader fields can change during
    # an otherwise valid download. Pin only identity, custody and byte fields.
    return {
        **{key: release.get(key) for key in ('id', 'draft', 'published_at', 'tag_name', 'target_commitish')},
        'assets': sorted(
            (
                {key: asset.get(key) for key in ('id', 'name', 'size', 'state', 'digest')}
                for asset in release.get('assets', [])
            ),
            key=lambda asset: asset['id'],
        ),
    }


def download(contract, directory):
    before = release_metadata(contract['release_id'])
    expected = validate_release(contract, before)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    for row in expected:
        with (directory / row['name']).open('xb') as output:
            # gh's supported API client owns GitHub's binary-asset redirect and
            # authentication behavior. No caller-supplied URL or token argv.
            result = subprocess.run(
                [
                    'gh',
                    'api',
                    f'repos/{REPOSITORY}/releases/assets/{row["asset_id"]}',
                    '-H',
                    'Accept: application/octet-stream',
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=900,
            )
            if result.returncode:
                raise RuntimeError('DRAFT_ASSET_DOWNLOAD_FAILED')
    after = release_metadata(contract['release_id'])
    validate_release(contract, after)
    if stable_release_identity(before) != stable_release_identity(after):
        raise ValueError('DRAFT_CHANGED_DURING_DOWNLOAD')
    return verify_and_assemble(contract, directory)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True)
    a = p.parse_args()
    try:
        print(download(json.loads(a.contract.read_text()), a.directory))
    except Exception as error:
        print(json.dumps({'result': 'HOLD', 'failure_class': type(error).__name__}))
        raise SystemExit(2)
