"""Shared wiring for the domain-level dual-backend contract suites (ADR-0044 facade, ADR-0002 port).

``bind_store`` binds the module-level ``db`` handle that every ``database/*`` module imports
(``from ._client import db``) to **what each posture actually deploys**, then hands the test a neutral
store to seed and assert through. One definition, because four suites had drifted copies of it.

The binding is the part worth reading. ``database/_client.py`` returns the **raw Firestore SDK
client** whenever ``STORAGE_BACKEND=firestore``, and wraps the neutral facade **only** for the other
backends. So the pair we ship is:

    STORAGE_BACKEND=firestore  ->  raw google.cloud.firestore.Client
    STORAGE_BACKEND=mongo      ->  NeutralFirestoreClient(MongoDocumentStore)

Until 2026-08-21 these suites bound the Firestore side to the *facade over* ``FirestoreDocumentStore``
— a third configuration nothing deploys. For reads that mostly still isolated adapter divergence (the
same facade sat on both sides), but for transactions it was worse than imprecise: the facade's
transaction reaches for a session-aware private op family (``_get``/``_set``/… with ``session=``) that
exists on the Mongo adapter and the in-memory fake but not on the Firestore adapter and not in
``ports.py``, so the first transactional read died with ``AttributeError``. No contract suite could
cover a transaction on the Firestore side, and nothing said so — no suite tried (BACKLOG L30/L31).

Both sides seed and assert through a ``DocumentStore``, never through backend-shaped internals, so a
test body reads identically for either backend.
"""

from __future__ import annotations

import os
import pathlib
import re
from typing import Any

import pytest

from tests.store_fakes import install_fake_db_client


# ``db`` is a lazy proxy that resolves through the accessor on every call, so patching the accessor is
# enough for it. ``get_firestore_client`` is NOT: several domain modules import the FUNCTION OBJECT at
# module load, so patching ``_client.get_firestore_client`` never reaches them. On the mongo leg those
# functions kept calling the real accessor -- which, with FIRESTORE_EMULATOR_HOST set for the other leg,
# quietly talked to the EMULATOR and returned nothing. A test that then asserted "no rows" would have
# passed for the wrong reason (BACKLOG L1, same class as L30/L31).
#
# Computed, not listed. The first version of this was a hand-written tuple built from a grep for
# ``from ._client import ...`` -- which missed ``from database._client import ...``, and the very next
# suite tripped over the module that uses the absolute form. A fact about the import graph does not
# belong in a literal.
_ACCESSOR_IMPORT = re.compile(r'^from (?:\.|database\.)_client import (?P<names>.+)$', re.M)


def _accessor_importers() -> list[str]:
    """``database.*`` modules that bind ``get_firestore_client`` as a module-level name."""
    domain = pathlib.Path(__file__).resolve().parents[2] / 'database'
    found = []
    for path in sorted(domain.glob('*.py')):
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in _ACCESSOR_IMPORT.finditer(text):
            if 'get_firestore_client' in match.group('names'):
                found.append(f'database.{path.stem}')
                break
    return found


def _bind_accessor(monkeypatch, client) -> None:
    """Point every binding of ``get_firestore_client`` at this backend's client."""
    import importlib

    from database import _client

    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(_client, '_firestore_client', client, raising=False)
    importers = _accessor_importers()
    assert importers, 'the accessor scan found nothing — the import pattern or the tree moved'
    for name in importers:
        module = importlib.import_module(name)
        # raising=True: if a module stops binding the name, the scan and the module disagree and the
        # blind spot is back. Fail here, where the reason is written down.
        monkeypatch.setattr(module, 'get_firestore_client', lambda: client)


@pytest.fixture(params=["firestore", "mongo"])
def bind_store(request, monkeypatch) -> Any:
    """Bind ``db`` to the production client for this backend; yield a neutral seeding store.

    Skips per-backend when that service's env is absent — but a per-backend SKIPPED means the suite
    proved half of what its name claims, which is how two of these suites sat dead for months. Check
    the counts: every test should appear twice.
    """
    from database import _client

    if request.param == "firestore":
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from google.cloud import firestore as _fs

        from database.store.adapters.firestore import FirestoreDocumentStore

        client = _fs.Client(project=os.environ.get("FIREBASE_PROJECT_ID", "demo-omi-local"))
        _bind_accessor(monkeypatch, client)
        # Explicit client on the seeding store too: its default is the lazy ``db`` boundary handle,
        # which resolves through the accessor patched just above.
        yield FirestoreDocumentStore(client=client)
        return

    uri = os.environ.get("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI not set")
    from database.store.adapters.mongo import MongoDocumentStore

    # yield + close: MongoDocumentStore owns a MongoClient, and a plain return leaves its pooled
    # connections open for every parametrized test, accumulating across the suite.
    store = MongoDocumentStore(uri=uri, db_name="omi_contract")
    try:
        from database.store.firestore_facade import NeutralFirestoreClient

        install_fake_db_client(monkeypatch, store=store)
        _bind_accessor(monkeypatch, NeutralFirestoreClient(store))
        yield store
    finally:
        store.close()
