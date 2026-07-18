"""Tests for the Firestore model-read boundary AST ratchet."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_firestore_model_read_boundary.py'
_SPEC = importlib.util.spec_from_file_location('check_firestore_model_read_boundary', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_counts_direct_assigned_and_model_validate_construction():
    source = '''
from models.other import Person

payload = {'id': 'p1'}
direct = Person(**payload)
assigned_payload = payload
assigned = Person(**assigned_payload)
validated = Person.model_validate(assigned_payload)
'''

    assert _MODULE.count_model_constructions(source) == 3


def test_counts_qualified_model_imports_and_keyword_model_validate():
    source = '''
import models.other as other
from models import another

first = other.Person(**payload)
second = other.Person.model_validate(obj=payload)
third = another.Person(**payload)
fourth = another.Person.model_validate(obj=payload)
'''

    assert _MODULE.count_model_constructions(source) == 4


def test_ignores_non_model_kwargs_and_excludes_boundary_file(tmp_path):
    source = '''
from google.cloud import firestore

client = firestore.Client(**kwargs)
'''
    assert _MODULE.count_model_constructions(source) == 0

    scan_root = tmp_path / 'backend' / 'database'
    scan_root.mkdir(parents=True)
    (scan_root / 'read_boundary.py').write_text('from models.other import Person\nrecord = Person(**payload)\n')
    (scan_root / 'reader.py').write_text('from models.other import Person\nrecord = Person(**payload)\n')

    assert _MODULE.collect_counts(tmp_path, Path('backend/database')) == {'backend/database/reader.py': 1}


def test_reports_only_count_increases():
    assert _MODULE.violations({'backend/database/readers.py': 2}, {'backend/database/readers.py': 1}) == [
        'backend/database/readers.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/database/readers.py': 1}, {'backend/database/readers.py': 2}) == []
