"""Shared pytest fixtures for the WhatsApp plugin tests.

Two design notes:

1. **OMI_DEV_MODE default**: P1.1 fix requires WHATSAPP_APP_SECRET or
   OMI_DEV_MODE=1 to allow module load. Default to dev mode here so the
   standard test command works without extra env vars. Tests that need real
   verification set WHATSAPP_APP_SECRET explicitly via monkeypatch.

2. **sys.modules isolation (runtime swap via autouse fixture)**: when the
   WhatsApp test suite runs together with the Telegram test suite in one
   pytest invocation, both plugins' `main` / `simple_storage` /
   `whatsapp_client` modules would otherwise collide on the bare names in
   sys.modules. Telegram's tests load theirs at module-collection time and
   reference them again at test-runtime via `from main import app` inside
   test functions, so any permanent pre-load would break Telegram.

   The fix: an autouse fixture in this conftest.py that, BEFORE each
   WhatsApp test runs, snapshots sys.modules['main' | 'simple_storage' |
   'whatsapp_client'] (preserving Telegram's values) and swaps them to our
   loaded versions. AFTER the test, restores the original snapshot. The
   fixture only fires for tests under this plugin's directory (pytest's
   conftest scoping), so Telegram tests are unaffected. Patches that target
   "main.whatsapp_client.send_message" etc. resolve correctly because the
   swap happens before the test starts.

   Test files should use `from conftest import load_main_module,
   load_simple_storage` for module-level references (the load is cached and
   the returned module is the same one the autouse fixture installs into
   sys.modules).
"""

import os
import sys
import importlib.util

import pytest

# Default to dev mode for the test suite.
os.environ.setdefault("OMI_DEV_MODE", "1")

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "..", "_shared"))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_HERE, ".."))

# Add plugins/_shared/ to sys.path so `import persona_client` works.
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

# Add the plugin's own directory to sys.path so `import simple_storage`
# / `import whatsapp_client` / `import main` works at collection time
# (before the autouse fixture has installed the conftest's loaded
# versions into sys.modules). The conftest's sys.modules swap below
# covers the test-run-time state; this sys.path entry covers the
# collection-time imports. Without it, `import simple_storage` at
# the top of test_storage_durability.py fails with ModuleNotFoundError
# because simple_storage.py lives in plugins/omi-whatsapp-app/, not on
# sys.path by default.
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)


# ---------------------------------------------------------------------------
# sys.modules isolation — load WhatsApp's plugin modules on demand, swap
# them into sys.modules for the duration of each WhatsApp test, and
# restore afterwards.
# ---------------------------------------------------------------------------

_OMI_WHATSAPP_PREFIX = "_omi_whatsapp_app"

# Cache loaded modules across tests (loaded once, reused).
_cached_modules: dict[str, object] = {}


def _load_omi_whatsapp_module(name: str):
    """Load the WhatsApp plugin's `<name>.py` via importlib and return it.

    Loaded module is cached so the second call is a dict lookup. The
    module is also registered under `<prefix>.<name>` in sys.modules for
    caching purposes.

    Bare-name registration (e.g. sys.modules['main']) is handled by callers:
    the autouse fixture below handles it at test runtime; the
    `load_main_module()` helper handles it temporarily during the main.py
    load (because main.py's own imports need to resolve).
    """
    cached = _cached_modules.get(name)
    if cached is not None:
        return cached

    spec = importlib.util.spec_from_file_location(
        f"{_OMI_WHATSAPP_PREFIX}.{name}",
        os.path.join(_PLUGIN_ROOT, f"{name}.py"),
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load plugin module spec for {name}.py")

    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{_OMI_WHATSAPP_PREFIX}.{name}"] = module
    spec.loader.exec_module(module)
    _cached_modules[name] = module
    return module


def load_main_module():
    """Load WhatsApp's `main.py` and return the loaded module object.

    Pre-loads simple_storage and whatsapp_client so main.py's imports
    resolve correctly. Temporarily swaps the bare-name sys.modules entries
    for the duration of the load, then restores — so Telegram's modules
    remain intact (this is safe because the function isn't called at
    Telegram test time).
    """
    # Pre-load dependencies (cached).
    our_simple_storage = _load_omi_whatsapp_module("simple_storage")
    our_whatsapp_client = _load_omi_whatsapp_module("whatsapp_client")

    # Snapshot current bare-name entries.
    saved = {
        "simple_storage": sys.modules.get("simple_storage"),
        "whatsapp_client": sys.modules.get("whatsapp_client"),
    }

    # Swap so main.py's `import simple_storage` / `import whatsapp_client`
    # resolve to our versions.
    sys.modules["simple_storage"] = our_simple_storage
    sys.modules["whatsapp_client"] = our_whatsapp_client

    try:
        return _load_omi_whatsapp_module("main")
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def load_simple_storage():
    """Load WhatsApp's `simple_storage.py` and return the loaded module."""
    return _load_omi_whatsapp_module("simple_storage")


def load_whatsapp_client():
    """Load WhatsApp's `whatsapp_client.py` and return the loaded module."""
    return _load_omi_whatsapp_module("whatsapp_client")


# ---------------------------------------------------------------------------
# Autouse fixture — runs for every test under this directory. Swaps the
# bare-name sys.modules entries to WhatsApp's versions for the test's
# duration, then restores them.
# ---------------------------------------------------------------------------

_BARE_NAMES = ("simple_storage", "whatsapp_client", "main")


@pytest.fixture(autouse=True)
def _whatsapp_sys_modules_isolation():
    """Snapshot + swap sys.modules[bare_name] to WhatsApp's; restore after."""
    # Pre-load all three (cached; idempotent).
    our_modules = {name: _load_omi_whatsapp_module(name) for name in _BARE_NAMES}

    # Snapshot current bare-name entries (could be Telegram's, could be None).
    saved = {name: sys.modules.get(name) for name in _BARE_NAMES}

    # Swap to our versions.
    for name, module in our_modules.items():
        sys.modules[name] = module

    # Reset module-level state that would otherwise leak across tests. Added
    # when the cubic P2 dedup fix was applied (the in-memory _seen_wamids
    # OrderedDict was retaining entries between tests because the module
    # object is shared across the test process).
    main_module = our_modules["main"]
    if hasattr(main_module, "_seen_wamids"):
        main_module._seen_wamids.clear()

    # Cubic review 4614271733 P3: clear simple_storage's module-level
    # `users` and `pending_setups` dicts at the start of every test.
    # Without this, the test_storage_durability tests (and any future
    # tests that exercise the storage layer) leave entries behind that
    # pollute subsequent tests' state. Unique keys prevent collisions
    # TODAY, but order-dependent failures are fragile. Pattern is
    # consistent with the existing _seen_wamids.clear() reset above.
    simple_storage_module = our_modules["simple_storage"]
    if hasattr(simple_storage_module, "users"):
        simple_storage_module.users.clear()
    if hasattr(simple_storage_module, "pending_setups"):
        simple_storage_module.pending_setups.clear()

    try:
        yield
    finally:
        # Restore the original bare-name entries.
        for name in _BARE_NAMES:
            original = saved.get(name)
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
