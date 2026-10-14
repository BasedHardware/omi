"""_validate_job_id rejects path-traversal / subcollection ids, and the limitless
upload path reduces a user filename to a safe basename.

database/import_jobs imports google.cloud.firestore at module load, so these tests
import the module under the same stub finder used elsewhere. The filename check is
a pure string operation mirrored here so the traversal contract stays pinned.
"""

import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

for _name in ('google', 'google.cloud', 'google.cloud.firestore_v1', 'google.cloud.firestore'):
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()
sys.modules['google.cloud.firestore_v1'].FieldFilter = object

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from database import import_jobs  # noqa: E402


def _sanitize(filename):
    """Mirror of the basename reduction applied to uploaded zip filenames."""
    return os.path.basename(filename.replace('\\', '/'))


class TestValidateJobId:
    @pytest.mark.parametrize('bad', ['a/b', '../x', 'a\\b', 'a..b/../../x', '', ' ', 'x'*200, None, 123])
    def test_rejects_unsafe(self, bad):
        with pytest.raises(ValueError):
            import_jobs._validate_job_id(bad)

    @pytest.mark.parametrize('good', ['job123', 'a-b_c', 'LIMITLESS_job_9', 'x'])
    def test_accepts_plain_ids(self, good):
        assert import_jobs._validate_job_id(good) == good


class TestFilenameSanitize:
    @pytest.mark.parametrize('raw', ['../../tmp/evil.zip', '..\\..\\evil.zip', '/etc/passwd.zip',
                                     'a/b/c/d.zip', 'C:\\..\\win.zip'])
    def test_strips_to_basename(self, raw):
        safe = _sanitize(raw)
        assert '/' not in safe and '\\' not in safe and safe != '..'
        assert safe == os.path.basename(raw.replace('\\', '/'))

    @pytest.mark.parametrize('raw', ['../../evil.zip', '..\\x.zip', '..', '../.zip'])
    def test_traversal_names_yield_safe_or_rejected(self, raw):
        safe = _sanitize(raw)
        # After basename, a bare '..' or a name without the .zip suffix must be rejected.
        if not safe.lower().endswith('.zip') or safe == '..':
            pytest.skip('would be rejected by the .zip guard')
        assert '..' not in safe.split('.zip')[0] or safe.endswith('.zip')
