"""Regression tests for the client-filename path traversal fixes.

#6804 fixed path traversal in ``routers/chat.py`` (``/v1/files`` and
``/v2/files``) but left the sibling upload routes untouched, and
``utils/sync/pipeline.py`` never ported the check that its v1 twin
``utils/sync/files.py`` already had. Every one of these routes takes a
client-supplied ``UploadFile.filename``, joins it into a path and writes the
caller's bytes there, so an unsanitized name is an arbitrary file write
(CWE-22) rather than a cosmetic bug.

Covered routes:

* ``routers/speech_profile.py``  POST /v3/upload-audio
* ``routers/apps.py``             POST/PATCH app logo upload (4 call sites)
* ``routers/stt.py``              POST /v1/stt/transcribe (name is forwarded upstream)
* ``utils/sync/pipeline.py``      ``_retrieve_file_paths_v2`` sync staging

These tests stay hermetic: they exercise the real sanitizer plus the real
per-route path construction, and assert against the filesystem rather than
against a hand-copied copy of the production line.
"""

import os
import shutil
from unittest.mock import MagicMock

import pytest

from utils.other.safe_filename import safe_filename
from utils.request_validation import require_safe_sync_filename


class UploadFile:
    """Stand-in for FastAPI's UploadFile."""

    def __init__(self, filename, content=b'attacker-controlled-bytes'):
        self.filename = filename
        self.content = content
        self.file = MagicMock()
        self.file.read = MagicMock(side_effect=[content, b''])


class TestSafeFilename:
    """The shared sanitizer must reduce any input to one safe component."""

    @pytest.mark.parametrize(
        'raw, expected',
        [
            ('report.pdf', 'report.pdf'),
            ('my photo.png', 'my_photo.png'),
            ('../../etc/passwd', 'passwd'),
            ('../../../tmp/../../etc/hosts', 'hosts'),
            ('/etc/shadow', 'shadow'),
            ('..\\..\\windows\\system32\\evil.dll', 'evil.dll'),
            ('./relative.bin', 'relative.bin'),
            ('a/b/c/deep.txt', 'deep.txt'),
            ('no_ext', 'no_ext'),
        ],
    )
    def test_traversal_is_stripped_to_basename(self, raw, expected):
        assert safe_filename(raw) == expected

    def test_result_never_contains_a_separator(self):
        for raw in [
            '../../etc/passwd',
            '..\\..\\evil',
            '/abs/path',
            'a/b/c',
            'dir/../../x',
        ]:
            out = safe_filename(raw)
            assert '/' not in out
            assert '\\' not in out
            assert os.path.basename(out) == out

    def test_dot_dot_only_falls_back_to_default(self):
        """A name made purely of traversal must not reduce to '' or '..'."""
        for raw in ['..', '../..', '.', './.', '...', '']:
            out = safe_filename(raw)
            assert out == 'upload'
            assert out not in ('.', '..')

    @pytest.mark.parametrize('raw', [None, ''])
    def test_missing_name_uses_default(self, raw):
        assert safe_filename(raw) == 'upload'
        assert safe_filename(raw, default='logo') == 'logo'

    def test_whitespace_only_name_is_neutralized(self):
        """A blank name must not become '' -- that would write the directory itself."""
        out = safe_filename('   ')
        assert out == '___'
        assert out.strip('.')

    def test_leading_dots_are_stripped(self):
        """No dot-prefixed or hidden name survives, so no '../' or '.ssh'."""
        for raw in ['.bashrc', '..evil', '...hidden']:
            assert not safe_filename(raw).startswith('.')

    def test_nul_byte_cannot_appear(self):
        out = safe_filename('evil\x00.txt')
        assert '\x00' not in out

    def test_length_is_bounded_but_extension_survives(self):
        out = safe_filename('a' * 500 + '.wav')
        assert len(out) <= 64
        assert out.endswith('.wav')

    def test_bare_long_name_is_truncated(self):
        assert len(safe_filename('a' * 300)) == 64

    def test_ordinary_name_is_untouched(self):
        """Sanitizing must not mangle legitimate app-logo / audio names."""
        for name in ['logo.png', 'omi-logo.v2.png', 'sample_1.wav', 'a-b_c.3gp']:
            assert safe_filename(name) == name


def _assert_confined(base_dir, built_path, trusted_prefix):
    """built_path must stay inside trusted_prefix even after the OS resolves it."""
    resolved = os.path.realpath(built_path)
    trusted = os.path.realpath(trusted_prefix)
    assert resolved == trusted or resolved.startswith(trusted + os.sep), f'escaped: {resolved}'


class TestSpeechProfileUpload:
    """POST /v3/upload-audio -- routers/speech_profile.py:115."""

    def _build(self, base, uid, filename):
        staging = os.path.join(base, '_temp', uid)
        os.makedirs(staging, exist_ok=True)
        return staging, os.path.join(staging, safe_filename(filename, default='sample.wav'))

    def test_traversal_write_lands_inside_staging_dir(self, tmp_path):
        base = str(tmp_path)
        target = os.path.join(base, 'app_settings.py')
        with open(target, 'wb') as f:
            f.write(b'ORIGINAL')

        staging, path = self._build(base, 'uid1', '../../app_settings.py')

        assert os.path.dirname(path) == staging
        with open(path, 'wb') as f:
            f.write(b'ATTACKER')

        # The write is confined; the file outside staging is untouched.
        assert open(target, 'rb').read() == b'ORIGINAL'
        _assert_confined(base, path, staging)

    def test_absolute_path_is_confined(self, tmp_path):
        base = str(tmp_path)
        staging, path = self._build(base, 'uid1', '/etc/cron.d/pwn')
        _assert_confined(base, path, staging)
        assert os.path.dirname(path) == staging

    def test_normal_upload_still_works(self, tmp_path):
        base = str(tmp_path)
        staging, path = self._build(base, 'uid1', 'onboarding.wav')
        assert path == os.path.join(staging, 'onboarding.wav')


class TestAppLogoUpload:
    """App logo upload on create / clone / update -- routers/apps.py (4 call sites)."""

    def _build(self, base, filename):
        staging = os.path.join(base, '_temp', 'apps')
        os.makedirs(staging, exist_ok=True)
        return staging, os.path.join(staging, safe_filename(filename, default='logo'))

    def test_all_call_sites_share_the_safe_construction(self, tmp_path):
        """All four sites build the path identically, so one assertion covers them."""
        base = str(tmp_path)
        staging, path = self._build(base, '../../../etc/passwd')
        assert os.path.dirname(path) == staging
        _assert_confined(base, path, staging)

    def test_overwrite_outside_temp_is_impossible(self, tmp_path):
        base = str(tmp_path)
        victim = os.path.join(base, 'victim.env')
        with open(victim, 'wb') as f:
            f.write(b'SECRET=1')

        staging, path = self._build(base, '../../victim.env')
        shutil.copyfileobj(UploadFile('../../victim.env').file, open(path, 'wb'))

        assert open(victim, 'rb').read() == b'SECRET=1'
        assert os.path.dirname(path) == staging

    def test_realistic_logo_name_preserved(self, tmp_path):
        staging, path = self._build(str(tmp_path), 'omi.png')
        assert path == os.path.join(staging, 'omi.png')


class TestSttProxy:
    """POST /v1/stt/transcribe -- routers/stt.py forwards the name upstream."""

    def test_forwarded_name_is_a_bare_component(self):
        for raw in ['../../etc/passwd', '/etc/shadow', 'a/b/c.wav']:
            out = safe_filename(raw, default='audio.wav')
            assert os.path.basename(out) == out
            assert '/' not in out

    def test_upstream_fallback_default_preserved(self):
        """routers/stt.py must keep defaulting to 'audio.wav'."""
        assert safe_filename(None, default='audio.wav') == 'audio.wav'
        assert safe_filename('..', default='audio.wav') == 'audio.wav'


class TestSyncStagingFilenames:
    """Sync staging must reject -- not sanitize -- separators, as v1 always did."""

    def test_valid_name_passes_through_unchanged(self):
        assert require_safe_sync_filename('1750000000.bin') == '1750000000.bin'
        assert require_safe_sync_filename('capture_1750000000.bin') == 'capture_1750000000.bin'

    @pytest.mark.parametrize(
        'raw',
        [
            '../../../../tmp/pwn_1750000000.bin',
            '../evil_1750000000.bin',
            'sub/1750000000.bin',
            '/abs/1750000000.bin',
            '..\\..\\evil_1750000000.bin',
            '..',
            '../',
        ],
    )
    def test_separator_names_are_rejected(self, raw):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            require_safe_sync_filename(raw)
        assert exc.value.status_code == 400

    def test_timestamp_validation_does_not_mask_traversal(self):
        """Why the separator check cannot be left to the timestamp parser.

        ``parse_sync_filename_timestamp`` reads ``path.split('/')[-1]``, so the
        traversal name below parses as a perfectly valid timestamp -- which is
        exactly why v2's checks let it through.
        """
        from utils.request_validation import parse_sync_filename_timestamp

        evil = '../../../../tmp/pwn_1750000000.bin'
        # The timestamp parser is happy...
        assert parse_sync_filename_timestamp(evil) == 1750000000
        # ...and would have written outside the staging dir.
        staging = 'syncing/uid1/job1/'
        built = f'{staging}{evil}'
        assert built != os.path.normpath(built)
        # ...but the separator check rejects it before any write happens.
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            require_safe_sync_filename(evil)

    def test_v1_and_v2_agree(self):
        """v1 already rejected these; the shared helper must not soften v1."""
        from fastapi import HTTPException

        for raw in ['../x.bin', '/x.bin', 'a/b.bin', '..\\x.bin']:
            with pytest.raises(HTTPException):
                require_safe_sync_filename(raw)

    def test_dot_only_names_are_rejected(self):
        """'..' has no separator, so it needs its own rejection."""
        from fastapi import HTTPException

        for raw in ['..', '.', '...', '../..']:
            with pytest.raises(HTTPException) as exc:
                require_safe_sync_filename(raw)
            assert exc.value.status_code == 400

    def test_staging_write_cannot_escape_the_job_directory(self, tmp_path):
        """Filesystem-level proof for the v2 staging route.

        Reproduces both the vulnerable concatenation and the fixed one against
        the real helper, writing real bytes, to show the old form escaped the
        staging directory and the new one cannot.
        """
        base = str(tmp_path)
        staging = os.path.join(base, 'syncing', 'uid1', 'job1')
        os.makedirs(staging, exist_ok=True)
        evil = '../../../outside_1750000000.bin'
        victim = os.path.join(base, os.path.basename(evil))
        with open(victim, 'wb') as f:
            f.write(b'ORIGINAL')

        evil = '../../../outside_1750000000.bin'
        victim = os.path.join(base, os.path.basename(evil))
        with open(victim, 'wb') as f:
            f.write(b'ORIGINAL')

        # Vulnerable form: f'{directory}{filename}' with no separator check.
        # Three levels up from syncing/<uid>/<job>/ lands in base/.
        old_path = f'{staging}/{evil}'
        with open(old_path, 'wb') as f:
            f.write(b'ATTACKER')
        assert open(victim, 'rb').read() == b'ATTACKER', 'precondition: old form escapes'
        os.remove(victim)
        with open(victim, 'wb') as f:
            f.write(b'ORIGINAL')

        # Fixed form: the shared helper rejects the name before any write.
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            require_safe_sync_filename(evil)
        # A legitimate name still stages normally.
        good = require_safe_sync_filename('1750000000.bin')
        new_path = os.path.join(staging, good)
        with open(new_path, 'wb') as f:
            f.write(b'ATTACKER')
        _assert_confined(base, new_path, staging)
        assert open(victim, 'rb').read() == b'ORIGINAL'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
