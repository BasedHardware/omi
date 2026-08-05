"""Tests for the object-store boundary AST ratchet (WP6 seal, ADR-0032/D14)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_object_store_boundary.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    # CI checks out the full repo, so the boundary guard still runs there.
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_object_store_boundary', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_flags_forbidden_client_imports():
    source = '''
from google.cloud import storage
import google.cloud.storage
from google.cloud.storage import Client
'''
    # 3 forbidden import statements above.
    assert _MODULE.count_boundary_violations(source) == 3


def test_flags_raw_blob_ops_regardless_of_receiver():
    source = '''
blob.upload_from_filename(path)
blob.upload_from_string(data, content_type="x")
b.upload_from_file(fh)
data = blob.download_as_bytes()
blob.download_to_filename(dst)
bucket.copy_blob(src, bucket, new)
blob.make_public()
list(bucket.list_blobs(prefix=p))
url = blob.generate_signed_url(version="v4")
'''
    # 9 raw blob/bucket-op method calls.
    assert _MODULE.count_boundary_violations(source) == 9


def test_flags_raw_blob_deletion():
    # Regression: raw GCS Blob deletion escaped the method-name list (a bare ``.delete`` collides with
    # dict/ORM APIs, so it can't just be listed). Receiver/type-aware: the blob factory chain, a
    # ``blob``/``*_blob`` receiver, and the distinctive bucket ``delete_blob(s)`` methods are caught.
    source = '''
bucket.blob(key).delete()          # blob factory chain
bucket.get_blob(key).delete()      # get_blob factory chain
blob.delete()                      # a Blob handed across a module boundary
self._blob.delete()                # *_blob receiver
bucket.delete_blob(name)           # distinctive bucket method
bucket.delete_blobs(names)         # distinctive bucket method
'''
    assert _MODULE.count_boundary_violations(source) == 6


def test_blob_delete_does_not_flag_the_port_or_unrelated_delete():
    # The blessed port form and unrelated ``.delete()`` receivers must NOT trip the guard.
    source = '''
from utils.object_store import get_object_store

get_object_store().delete(bucket, key)   # the neutral port
store.delete(bucket, key)                # port handle
session.delete(row)                      # ORM
cache.delete(cache_key)                  # cache
os.remove(path)
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_ignores_the_neutral_port_and_unrelated_code():
    source = '''
from utils.object_store import get_object_store, ObjectNotFound

store = get_object_store()
store.put(bucket, key, data, content_type="image/png")
raw = store.get_bytes(bucket, key)
url = store.presign_get(bucket, key, expires_seconds=300)
public = store.public_url(bucket, key)
store.set_metadata(bucket, key, {"a": "b"})
value = some_dict.get("key")
tokens = rate_limiter.bucket(user)      # "bucket" as a domain word must not trip the guard
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_collect_counts_excludes_boundary_and_allowlisted_dirs(tmp_path):
    backend = tmp_path / 'backend'
    for rel in ('utils/object_store', 'tests', 'testing', 'scripts', 'agent-proxy', 'routers'):
        (backend / rel).mkdir(parents=True)
    leak = 'from google.cloud import storage\nx = storage.Client().bucket("b").blob("k").upload_from_filename("f")\n'
    (backend / 'utils' / 'object_store' / 'adapters.py').write_text(leak)  # boundary: allowed
    (backend / 'tests' / 'test_x.py').write_text(leak)                     # tests: allowed
    (backend / 'testing' / 'harness.py').write_text(leak)                  # testing: allowed
    (backend / 'scripts' / 'oneoff.py').write_text(leak)                   # scripts: allowed
    (backend / 'agent-proxy' / 'main.py').write_text(leak)                 # separate service: allowed
    (backend / 'routers' / 'leaky.py').write_text(leak)                    # runtime router: FLAGGED

    counts = _MODULE.collect_counts(tmp_path, Path('backend'))
    assert counts == {'backend/routers/leaky.py': 2}


def test_reports_only_count_increases_over_baseline():
    assert _MODULE.violations({'backend/routers/x.py': 2}, {'backend/routers/x.py': 1}) == [
        'backend/routers/x.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/routers/x.py': 1}, {'backend/routers/x.py': 1}) == []


def test_s3_client_construction_is_flagged():
    # The S3 backend must be reached through the port too; a raw boto3 s3 client outside it is flagged.
    assert _MODULE.count_boundary_violations("import boto3\nboto3.client('s3')\nboto3.resource('s3')\n") == 2


def test_non_s3_boto3_client_is_not_a_false_positive():
    assert _MODULE.count_boundary_violations("import boto3\nboto3.client('dynamodb')\n") == 0


def test_raw_blob_methods_beyond_delete_are_flagged():
    # Regression: open/exists/patch on a blob-like receiver bypassed the delete-only check.
    assert _MODULE.count_boundary_violations("blob.open('r')\nx_blob.exists()\nbucket.blob(k).patch()\n") == 3


def test_neutral_port_methods_are_not_false_positives():
    assert _MODULE.count_boundary_violations("get_object_store().exists(k)\nget_object_store().delete(k)\n") == 0


def test_literal_dynamic_import_of_gcs_is_flagged():
    assert _MODULE.count_boundary_violations(
        "import importlib\nimportlib.import_module('google.cloud.storage')\n"
    ) == 1


def test_load_baseline_rejects_boolean_counts(tmp_path):
    import json

    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'backend/x.py': True}))
    with pytest.raises(ValueError):
        _MODULE.load_baseline(path)
