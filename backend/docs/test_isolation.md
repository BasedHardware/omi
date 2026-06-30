# Backend Test Isolation & Import Purity

> The committed prescription for keeping the backend unit suite single-process-safe.
> Working state (progress, migration ledger, decision log) lives in
> `.coordination/test-isolation/` (git-ignored). Start there if you are mid-migration.

## Why this exists

The backend unit suite cannot run in a single pytest process: ~100 test files mutate
`sys.modules` at module scope to paper over **import-time side effects in production
code** (clients constructed at import, credential reads, artifact downloads, heavy
chains pulled in eagerly). The runner hides this by spawning one pytest process per
file. That isolation is a palliative and the ceiling on speed, hermeticity, and
confidence. This effort removes the root cause instead of managing the symptom.

## The two tiers

### Tier 1 — Import purity (production code)

**Rule.** A backend module's top level must be referentially transparent. Importing
it must not:

- perform IO or network calls (`open(...)`, `requests.*`, `urllib...`, `httpx.*` at
  module top level);
- read the environment in a way that can raise or branch without a safe default —
  `os.environ["X"]` (subscript) at module scope is **banned**; `os.getenv("X")` and
  `os.environ.get("X")` are fine;
- construct resource-holding objects — clients, connections, downloaded artifacts
  (`OpenAI(...)`, `Redis(...)`, `Pinecone(...)`, `tiktoken.encoding_for_model(...)`,
  `firebase_admin.initialize_app(...)`, …) at module top level;
- mutate process-global state (`sys.modules`, registering handlers, …).

All such work moves into **lazy getters** or explicit app-startup initialization.

**Scope: side effects, not import duration.** Import purity targets *correctness*
side effects, not import *speed*. `import langchain` is slow but pure — that's xdist's
problem. This deliberately does **not** conflict with the existing rule *"No in-function
imports — all imports at module top level."* That rule stays: we defer *construction*,
not *imports*.

**Mechanical fix (the 80%).** Wrap a top-level client in a lazy getter:

```python
# BEFORE (banned): constructs at import; fails without credentials; forces tests to stub.
from openai import OpenAI
client = OpenAI()

# AFTER (import-pure): construction deferred to first use; tests inject a fake.
from openai import OpenAI
_client = None
def get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client
```

**Deeper fix (logic layer).** Extract pure functions from IO-ful wiring and test those
directly, without importing the app. *Functional core, imperative shell* is the target
for new logic code — the unit tests that matter most test pure functions, and those
never needed stubs.

**Router seam.** FastAPI `Depends(...)` + `app.dependency_overrides` already exist
(`dependencies.py` uses them). For router tests, override dependencies — do **not**
patch `sys.modules` of `database.*`.

**Enforcement.** `backend/scripts/scan_import_time_side_effects.py` — AST scanner
(curated side-effecting constructors + `os.environ[]` subscript + top-level
network/IO). Escape valve: deprecated legacy allowlist +
`# noqa: import-side-effect: <reason>` pragma (reason **required**, auditable).

### Tier 2 — Sanctioned seams (test code)

**Rule.** Test modules must **not** mutate `sys.modules` at module scope. Permitted:

1. **`monkeypatch.setattr(module, "_singleton", fake)`** on a lazy-held singleton — a
   module-attribute patch (auto-restored at fixture teardown), **not** a `sys.modules`
   replacement. This is the default seam.
2. **FastAPI `app.dependency_overrides`** for router dependencies.
3. **conftest session stubs** *only* for genuinely-optional third-party packages not
   installed in CI (prometheus_client, redis, cachetools, tiktoken) — the existing
   `tests/conftest.py` pattern. This is legitimate conftest territory.
4. **Reserve only:** `backend/testing/import_isolation.py` → `stub_modules(...)`
   context manager (or `AutoMockModule`) for the rare case a fake must be active
   *before* the target imports. Use inside a fixture/function, never at module scope.

The legacy `tests/unit/memory_import_isolation.py` (hand-rolled snapshot/restore +
`AutoMockModule` + `install_*`) is **deprecated** — do not extend it; migrate its
consumers to (1)/(2). Its restore is best-effort and unprovable.

**Enforcement.** `backend/scripts/check_module_stub_pollution.py` — AST hard gate
covering all module-scope `sys.modules` mutation forms. Allowlist = conftest + the
reserve helper + a deprecated legacy list. **No pragma for Tier 2** — the sanctioned
mechanism exists, so there is no excuse.

## Migration recipe (concrete before/after)

A typical dirty test looks like this (module scope):

```python
# BEFORE — banned: leaks across tests.
sys.modules["database.vector_db"] = types.ModuleType("database.vector_db")
sys.modules["database.vector_db"].find_similar_memories = lambda *a, **k: []
import database.vector_db  # picks up the fake
```

Migrate to a fixture-scoped `monkeypatch`:

```python
# AFTER — hermetic: restored at fixture teardown.
import pytest

@pytest.fixture
def fake_vector_db(monkeypatch):
    from testing.import_isolation import AutoMockModule
    fake = AutoMockModule("database.vector_db")
    fake.find_similar_memories = lambda *a, **k: []
    # If the production module is already imported, patch its attribute:
    import database.vector_db as real  # works because Tier-1 made import cheap
    monkeypatch.setattr(real, "find_similar_memories", fake.find_similar_memories)
    return real

def test_thing(fake_vector_db):
    ...
```

If the production module *cannot* be imported cheaply yet (Tier-1 not done for that
module), use the reserve finder:

```python
@pytest.fixture
def fake_vector_db():
    from testing.import_isolation import AutoMockModule, stub_modules
    fake = AutoMockModule("database.vector_db")
    with stub_modules({"database.vector_db": fake}):
        yield fake
```

After migrating: remove the file from `backend/tests/.module_stub_legacy_allowlist`,
add it to `backend/tests/.single_process_safe_subset`, run the file's tests and the
hermeticity guard.

## How to add a new test

1. Prefer testing a pure function — no stubs needed.
2. If you need a fake dependency: is the production module import-cheap (Tier 1)? Then
   `monkeypatch.setattr` on its lazy-held singleton.
3. Router dependency? `app.dependency_overrides`.
4. Optional third-party package not installed in CI? Add the stub to `tests/conftest.py`
   (session scope), not your test file.
5. Only if none of the above suffice: the reserve `stub_modules` finder, inside a fixture.
6. **Never** write `sys.modules[...] = ...` at module scope. The checker will reject it.

## Enforcement summary

| Gate | Scope | When | Escape |
|------|-------|------|--------|
| `scan_import_time_side_effects.py` | production import purity | pre-push (changed) + CI (full) | pragma w/ reason + shrinking legacy list |
| `check_module_stub_pollution.py` | test `sys.modules` mutation | pre-push (changed) + CI (full) | shrinking legacy list (no pragma) |
| `test_sys_modules_hermeticity.py` | clean subset leaves no stubs | pytest (CI) | none — a failure means the subset is not safe |
| pre-push monotonic check | allowlists only shrink | pre-push | none |

## Terminal state

Done when: both allowlists are empty (deleted), `test.sh` runs the whole unit suite as
one `pytest` invocation, the hermeticity guard covers the full suite, and
`memory_import_isolation.py` is gone. See `.coordination/test-isolation/PLAN.md` §4.
