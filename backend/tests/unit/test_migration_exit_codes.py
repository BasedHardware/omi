"""Migration scripts must exit NON-ZERO when a worker fails.

002_populate_historical_usage and 006_auto_set_transcription_mode fan their per-user work out across a
ThreadPoolExecutor and swallow each worker's exception (logging it, counting it) so one bad user does
not abort the sweep. Before the fix they still returned a clean exit code, so a caller/CI that only
checks ``$?`` read a partially-applied backfill as a full success and the failed users were silently
never retried (cubic PR 10887 002:67 / 006:64).

These load each migration by path with its heavy backend imports stubbed, then drive ``main()`` through
its real fan-out with one worker forced to raise, asserting the process exits 1 — and exits cleanly when
every worker succeeds. Behavioral (runs the real loop + exit logic), not a source-string tripwire."""

import importlib.util
import os
import sys
import types

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIG_DIR = os.path.join(BACKEND_DIR, "migrations")


def _install_stubs(leaf_modules):
    """Register stub modules (dotted name -> module) plus their parent packages in sys.modules.

    Isolates the migration from the real backend so importing it is hermetic. Returns a restore fn."""
    all_names = set()
    for name in leaf_modules:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            all_names.add(".".join(parts[:i]))

    saved = {name: sys.modules.get(name) for name in all_names}
    for name in sorted(all_names):  # parents before children (alpha order on dotted names)
        mod = leaf_modules.get(name) or types.ModuleType(name)
        mod.__path__ = []  # mark as a package so submodule imports resolve from sys.modules
        sys.modules[name] = mod
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, mod)

    def restore():
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    return restore


def _load(filename, leaf_modules):
    restore = _install_stubs(leaf_modules)
    try:
        path = os.path.join(MIG_DIR, filename)
        spec = importlib.util.spec_from_file_location(f"_mig_{filename.replace('.', '_')}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, restore
    except Exception:
        restore()
        raise


def _leaf(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# --- 002 ------------------------------------------------------------------------------------------

def _load_002():
    return _load(
        "002_populate_historical_usage.py",
        {
            "database.store": _leaf("database.store", get_document_store=lambda: None),
            "database.user_usage": _leaf("database.user_usage"),
            "models.conversation": _leaf("models.conversation", Conversation=object),
            "models.memories": _leaf("models.memories", MemoryDB=object),
            "utils.encryption": _leaf("utils.encryption"),
        },
    )


def test_002_exits_nonzero_when_a_worker_fails(monkeypatch):
    mod, restore = _load_002()
    try:
        def _worker(uid):
            if uid == "bad":
                raise RuntimeError("boom")

        monkeypatch.setattr(mod, "migrate_user_usage", _worker)
        # --uids bypasses the store; both users are fanned out, one raises.
        monkeypatch.setattr(sys, "argv", ["002", "--uids", "ok,bad"])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 1
    finally:
        restore()


def test_002_exits_clean_when_all_workers_succeed(monkeypatch):
    mod, restore = _load_002()
    try:
        monkeypatch.setattr(mod, "migrate_user_usage", lambda uid: None)
        monkeypatch.setattr(sys, "argv", ["002", "--uids", "ok1,ok2"])
        mod.main()  # returns normally, no SystemExit
    finally:
        restore()


# --- 006 ------------------------------------------------------------------------------------------

class _Doc:
    def __init__(self, doc_id):
        self.id = doc_id


def _load_006():
    return _load(
        "006_auto_set_transcription_mode.py",
        {
            "database.store": _leaf("database.store", get_document_store=lambda: None),
            "utils.stt.streaming": _leaf("utils.stt.streaming", deepgram_nova3_multi_languages=set()),
        },
    )


def test_006_exits_nonzero_when_a_worker_fails(monkeypatch):
    mod, restore = _load_006()
    try:
        monkeypatch.setattr(mod, "get_all_users", lambda: [_Doc("ok"), _Doc("bad")])

        def _proc(user, dry_run=False):
            if user.id == "bad":
                raise RuntimeError("boom")
            return "updated"

        monkeypatch.setattr(mod, "process_user", _proc)
        monkeypatch.setattr(sys, "argv", ["006", "--dry-run"])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 1
    finally:
        restore()


def test_006_exits_clean_when_all_workers_succeed(monkeypatch):
    mod, restore = _load_006()
    try:
        monkeypatch.setattr(mod, "get_all_users", lambda: [_Doc("a"), _Doc("b")])
        monkeypatch.setattr(mod, "process_user", lambda user, dry_run=False: "updated")
        monkeypatch.setattr(sys, "argv", ["006", "--dry-run"])
        mod.main()  # returns normally, no SystemExit
    finally:
        restore()
