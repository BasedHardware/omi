"""Issue #21707 — a Finder-compressed ZIP must not count `__MACOSX/`
entries or `._*` AppleDouble siblings as lifelog files.

A real Limitless export re-zipped by Finder contains both
`lifelogs/x.md` (UTF-8 transcript) and `__MACOSX/lifelogs/._x.md`
(resource-fork bytes, undecodable). The old selector matched BOTH —
the AppleDouble decode raised and the job reported failed files.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = ('database', 'utils', 'firebase_admin', 'google', 'pusher',
         'modal', 'ulid', 'langchain', 'redis', 'sentry_sdk', 'pydub',
         'opuslib', 'pinecone', 'typesense', 'prometheus_client')


def _is_stubbed(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
sys.meta_path.insert(0, _f)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    import utils.imports.limitless as L
finally:
    sys.meta_path.remove(_f)


class TestMacosMetadataFiltering:
    def test_appledouble_and_macosx_dirs_are_not_lifelogs(self):
        names = [
            'lifelogs/2025-10-08_07h00m25s_Real.md',        # real
            'export/lifelogs/note.md',                    # real, nested
            '__MACOSX/lifelogs/._2025-10-08_07h00m25s_Real.md',  # AppleDouble
            'lifelogs/._2025-10-08_07h00m25s_Real.md',    # AppleDouble sibling
            '__MACOSX/._other.md',
            'lifelogs/img.png',                           # not markdown
            'random/readme.md',                           # no lifelogs/ path
        ]
        got = [n for n in names if L.is_lifelog_path(n)]
        assert got == [
            'lifelogs/2025-10-08_07h00m25s_Real.md',
            'export/lifelogs/note.md',
        ]

    def test_finder_compressed_zip_counts_no_failures(self):
        """End-to-end at the ZIP level: the enumeration a real Finder zip
        produces selects only the genuine transcript."""
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('lifelogs/real.md', '# Real\\nhello')
            z.writestr('lifelogs/._real.md', b'\\x00\\x05\\x16')  # AppleDouble
            z.writestr('__MACOSX/lifelogs/._real.md', b'\\x00\\x05')
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            selected = [n for n in z.namelist() if L.is_lifelog_path(n)]
        assert selected == ['lifelogs/real.md']
