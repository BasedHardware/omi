"""Validate Docker's existing OCI save, preserving compressed blob identities.

Host-side post-build tool. Does not alter frozen build inputs or run/publish an image.
"""

import gzip
import hashlib
import json
import re
import tarfile

MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
CONFIG = 'application/vnd.oci.image.config.v1+json'
PLAIN = {'application/vnd.oci.image.layer.v1.tar', 'application/vnd.docker.image.rootfs.diff.tar'}
GZIP = {'application/vnd.oci.image.layer.v1.tar+gzip', 'application/vnd.docker.image.rootfs.diff.tar.gzip'}


def digest(stream):
    return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(path, source_sha, build_inputs_sha, supervisor_sha):
    with tarfile.open(path) as archive:
        names = [m.name for m in archive.getmembers()]
        if len(names) != len(set(names)):
            raise ValueError('DUPLICATE_ARCHIVE_MEMBER')

        def stream(name):
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError('REGULAR_ARCHIVE_FILE_REQUIRED')
            return archive.extractfile(member)

        if json.load(stream('oci-layout')) != {'imageLayoutVersion': '1.0.0'}:
            raise ValueError('OCI_LAYOUT_REQUIRED')
        index = json.load(stream('index.json'))
        if index.get('schemaVersion') != 2 or len(index.get('manifests', [])) != 1:
            raise ValueError('ONE_OCI_IMAGE_REQUIRED')

        def blob(descriptor):
            identity = descriptor['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', identity):
                raise ValueError('SHA256_BLOB_REQUIRED')
            name = 'blobs/sha256/' + identity.split(':')[1]
            if archive.getmember(name).size != descriptor['size']:
                raise ValueError('BLOB_SIZE_MISMATCH')
            with stream(name) as content:
                if digest(content) != identity:
                    raise ValueError('BLOB_DIGEST_MISMATCH')
            return name

        descriptor = index['manifests'][0]
        if descriptor.get('mediaType') != MANIFEST:
            raise ValueError('OCI_MANIFEST_REQUIRED')
        manifest = json.load(stream(blob(descriptor)))
        if manifest.get('schemaVersion') != 2 or manifest.get('mediaType') != MANIFEST:
            raise ValueError('OCI_MANIFEST_REQUIRED')
        if manifest['config'].get('mediaType') != CONFIG:
            raise ValueError('OCI_CONFIG_REQUIRED')
        config = json.load(stream(blob(manifest['config'])))
        labels = config.get('config', {}).get('Labels', {})
        if config.get('os') != 'linux' or config.get('architecture') != 'amd64':
            raise ValueError('LINUX_AMD64_REQUIRED')
        if (
            labels.get('org.opencontainers.image.revision') != source_sha
            or labels.get('omi.build-inputs.sha256') != build_inputs_sha
            or labels.get('omi.supervisor.sha256') != supervisor_sha
        ):
            raise ValueError('BUILD_LABEL_MISMATCH')
        diff_ids = config['rootfs']['diff_ids']
        if config['rootfs'].get('type') != 'layers' or len(diff_ids) != len(manifest['layers']):
            raise ValueError('LAYER_COUNT_MISMATCH')
        checked = []
        for layer, expected_diff in zip(manifest['layers'], diff_ids):
            name = blob(layer)
            media = layer['mediaType']
            if media not in PLAIN | GZIP:
                raise ValueError('UNSUPPORTED_LAYER_ENCODING')
            with stream(name) as raw:
                if media in GZIP:
                    with gzip.GzipFile(fileobj=raw, mode='rb') as content:
                        actual_diff = digest(content)
                else:
                    actual_diff = digest(raw)
            if actual_diff != expected_diff:
                raise ValueError('UNCOMPRESSED_LAYER_IDENTITY_MISMATCH')
            checked.append(
                {'digest': layer['digest'], 'diff_id': actual_diff, 'size': layer['size'], 'mediaType': media}
            )
    return {
        'manifest_digest': descriptor['digest'],
        'config_digest': manifest['config']['digest'],
        'layers': checked,
        'config': config,
    }
