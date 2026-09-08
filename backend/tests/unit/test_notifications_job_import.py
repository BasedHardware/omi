import importlib
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODAL_DIR = BACKEND_DIR / 'modal'


def test_notifications_job_import_does_not_start_firebase_or_run_the_job(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    monkeypatch.syspath_prepend(str(MODAL_DIR))
    monkeypatch.delitem(sys.modules, 'job', raising=False)

    initialized = []
    firebase_admin = types.ModuleType('firebase_admin')
    firebase_admin.initialize_app = lambda *args, **kwargs: initialized.append((args, kwargs))
    jobs = types.ModuleType('utils.other.jobs')
    jobs.start_job = lambda: None
    monkeypatch.setitem(sys.modules, 'firebase_admin', firebase_admin)
    monkeypatch.setitem(sys.modules, 'utils.other.jobs', jobs)

    importlib.import_module('job')

    assert initialized == []
