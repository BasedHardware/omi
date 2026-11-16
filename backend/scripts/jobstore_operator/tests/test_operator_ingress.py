"""Verify pinned private-draft custody and exact input bytes with offline fakes."""

import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import copy
import hashlib
import tempfile
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
import operator_ingress as ingress


def inputs():
    parts = [b'first-fixed-bytes', b'second-fixed-bytes']
    rows = [
        {
            'name': f'operator.oci.tar.part-{i:03d}',
            'bytes': len(b),
            'sha256': hashlib.sha256(b).hexdigest(),
            'asset_id': i + 1,
        }
        for i, b in enumerate(parts)
    ]
    fixture = {'name': 'fixtures.tar.gz', 'bytes': 3, 'sha256': hashlib.sha256(b'fix').hexdigest(), 'asset_id': 3}
    c = {
        'repository': ingress.REPOSITORY,
        'source_sha': 'a' * 40,
        'release_tag': 'fixed-input',
        'release_id': 10,
        'parts': rows,
        'fixture': fixture,
        'archive_bytes': sum(map(len, parts)),
        'archive_sha256': hashlib.sha256(b''.join(parts)).hexdigest(),
    }
    r = {
        'id': 10,
        'draft': True,
        'published_at': None,
        'tag_name': 'fixed-input',
        'target_commitish': 'a' * 40,
        'assets': [
            {
                'id': x['asset_id'],
                'name': x['name'],
                'size': x['bytes'],
                'state': 'uploaded',
                'digest': 'sha256:' + x['sha256'],
            }
            for x in rows + [fixture]
        ],
    }
    return (c, r, parts)


class IngressTests(unittest.TestCase):

    def test_download_ignores_only_incidental_metadata_changes(self):
        c, before, parts = inputs()
        after = copy.deepcopy(before)
        after['assets'].reverse()
        for asset in after['assets']:
            asset.update(download_count=1, updated_at='later', label='new presentation')
        after['body'] = 'edited presentation'
        bodies = {row['asset_id']: body for row, body in zip(c['parts'] + [c['fixture']], parts + [b'fix'])}

        def binary(argv, **kwargs):
            kwargs['stdout'].write(bodies[int(argv[2].rsplit('/', 1)[1])])
            return subprocess.CompletedProcess(argv, 0)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'download'
            with patch.object(ingress, 'release_metadata', side_effect=[before, after]), patch.object(
                ingress.subprocess, 'run', side_effect=binary
            ):
                self.assertEqual(ingress.download(c, target).read_bytes(), b''.join(parts))

    def test_download_recheck_still_refuses_custody_or_byte_changes(self):
        mutations = [
            lambda r: r.update(draft=False),
            lambda r: r.update(target_commitish='b' * 40),
            lambda r: r['assets'][0].update(id=999),
            lambda r: r['assets'][0].update(digest='sha256:' + '0' * 64),
            lambda r: r['assets'][0].update(size=0),
            lambda r: r['assets'].pop(),
        ]
        for mutate in mutations:
            c, before, parts = inputs()
            after = copy.deepcopy(before)
            mutate(after)
            bodies = {row['asset_id']: body for row, body in zip(c['parts'] + [c['fixture']], parts + [b'fix'])}

            def binary(argv, **kwargs):
                kwargs['stdout'].write(bodies[int(argv[2].rsplit('/', 1)[1])])
                return subprocess.CompletedProcess(argv, 0)

            with self.subTest(after=after), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / 'download'
                with patch.object(ingress, 'release_metadata', side_effect=[before, after]), patch.object(
                    ingress.subprocess, 'run', side_effect=binary
                ):
                    with self.assertRaises(ValueError):
                        ingress.download(c, target)
                    self.assertFalse((target / 'operator.oci.tar').exists())

    def test_valid_exact_metadata_and_bytes(self):
        c, r, b = inputs()
        self.assertEqual(len(ingress.validate_release(c, r)), 3)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for row, body in zip(c['parts'] + [c['fixture']], b + [b'fix']):
                (d / row['name']).write_bytes(body)
            self.assertEqual(ingress.verify_and_assemble(c, d).read_bytes(), b''.join(b))

    def test_unstaged_contract_refuses_before_network(self):
        c, _, _ = inputs()
        c['release_id'] = None
        with patch.object(ingress, 'run') as run:
            with self.assertRaises(ValueError):
                ingress.download(c, Path('/unused'))
            run.assert_not_called()

    def test_published_or_wrong_release_refused(self):
        for key, value in (
            ('draft', False),
            ('published_at', 'now'),
            ('id', 11),
            ('tag_name', 'other'),
            ('target_commitish', 'b' * 40),
        ):
            c, r, _ = inputs()
            r[key] = value
            with self.assertRaises(ValueError):
                ingress.validate_release(c, r)

    def test_substituted_asset_metadata_refused(self):
        for key, value in (('id', 999), ('size', 0), ('digest', 'sha256:' + '0' * 64), ('state', 'new')):
            c, r, _ = inputs()
            r['assets'][0][key] = value
            with self.assertRaises(ValueError):
                ingress.validate_release(c, r)

    def test_extra_or_duplicate_asset_refused(self):
        for duplicate in (True, False):
            c, r, _ = inputs()
            if duplicate:
                r['assets'][1]['name'] = r['assets'][0]['name']
            else:
                r['assets'].append(copy.deepcopy(r['assets'][0]))
            with self.assertRaises(ValueError):
                ingress.validate_release(c, r)

    def test_wrong_repository_and_path_escape_refused(self):
        c, r, _ = inputs()
        c['repository'] = 'attacker/repository'
        with self.assertRaises(ValueError):
            ingress.validate_release(c, r)
        c, r, _ = inputs()
        c['parts'][0]['name'] = '../escape'
        with self.assertRaises(ValueError):
            ingress.validate_release(c, r)

    def test_part_substitution_refused(self):
        c, _, b = inputs()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for row, body in zip(c['parts'] + [c['fixture']], b + [b'fix']):
                (d / row['name']).write_bytes(body)
            (d / c['parts'][0]['name']).write_bytes(b'X' * len(b[0]))
            with self.assertRaisesRegex(ValueError, 'ASSET_BYTES_CHANGED'):
                ingress.verify_and_assemble(c, d)

    def test_reordered_parts_refused_by_combined_digest(self):
        c, _, b = inputs()
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for row, body in zip(c['parts'] + [c['fixture']], b + [b'fix']):
                (d / row['name']).write_bytes(body)
            c['parts'].reverse()
            with self.assertRaisesRegex(ValueError, 'COMBINED_ARCHIVE_CHANGED'):
                ingress.verify_and_assemble(c, d)


if __name__ == '__main__':
    unittest.main()
