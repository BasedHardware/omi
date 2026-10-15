"""_validate_job_id rejects path-traversal / subcollection ids, and the limitless
upload path reduces a user filename to a safe basename.

database/import_jobs imports google.cloud.firestore at module load, so these tests
import the module under the same stub finder used elsewhere. The filename check
imports the real safe_upload_basename helper the routers call — not a mirror —
so the traversal contract is pinned to production logic.
"""

import os
import sys
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
from utils.imports.upload_names import safe_upload_basename  # noqa: E402


class TestValidateJobId:
    @pytest.mark.parametrize('bad', ['a/b', '../x', 'a\\b', 'a..b/../../x', '', ' ', 'x' * 200, None, 123])
    def test_rejects_unsafe(self, bad):
        with pytest.raises(ValueError):
            import_jobs._validate_job_id(bad)

    @pytest.mark.parametrize('good', ['job123', 'a-b_c', 'LIMITLESS_job_9', 'x'])
    def test_accepts_plain_ids(self, good):
        assert import_jobs._validate_job_id(good) == good


class TestFilenameSanitize:
    @pytest.mark.parametrize(
        'raw', ['../../tmp/evil.zip', '..\\..\\evil.zip', '/etc/passwd.zip', 'a/b/c/d.zip', 'C:\\..\\win.zip']
    )
    def test_strips_to_basename(self, raw):
        safe = safe_upload_basename(raw)
        assert safe == 'evil.zip' or safe == 'passwd.zip' or safe == 'd.zip' or safe == 'win.zip'
        assert '/' not in safe and '\\' not in safe and safe != '..'

    @pytest.mark.parametrize('raw', [None, '', '..', '.', 'a/../../..', 'x\x00.zip'])
    def test_rejects_unusable(self, raw):
        assert safe_upload_basename(raw) is None

    def test_keeps_plain_names(self):
        assert safe_upload_basename('export.zip') == 'export.zip'
        assert safe_upload_basename('my file 2.zip') == 'my file 2.zip'
