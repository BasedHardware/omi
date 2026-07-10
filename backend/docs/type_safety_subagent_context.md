# Backend Type-Safety Migration — Subagent Context

## Objective
Enroll backend .py files into Pyright strict mode (reportUnknown* at warning).
Fix every file to **0 errors, 0 warnings** then add it to pyrightconfig.json.

## Worktree
`<repo-root>`

## Verify a file
```bash
cd $(git rev-parse --show-toplevel)/backend
.venv/bin/python -m pyright -p pyrightconfig.json <path> \
  --pythonpath .venv/bin/python --level warning --warnings
```
File is ready to enroll ONLY when output shows `0 errors, 0 warnings`.

## Full typecheck
```bash
cd $(git rev-parse --show-toplevel)/backend && bash scripts/typecheck.sh
```

## CRITICAL RULES
1. **NEVER run `git reset`, `git stash`, `git checkout -- .`, or any command that
   could revert uncommitted changes.** These destroy other agents' work.
2. **Only edit files you were explicitly assigned.** Do NOT fix upstream files
   to resolve your file's type errors — use `# type: ignore` or `cast()` instead.
3. **Do NOT spawn subagents.** Work serially to avoid edit collisions.
4. **Preserve runtime behavior EXACTLY.** Only change signatures, type annotations,
   boundary narrowing, and adapter insertion. NEVER change logic to satisfy the typechecker.
5. **No in-function imports.** All imports at module top level.
6. `def` (not `async def`) for sync endpoints. `async def` only when genuinely awaiting.
7. No new `TODO`/`FIXME`/`HACK` comments.

## Established Patterns (copy EXACTLY)

### Firestore read (most common)
```python
raw: object = doc.to_dict()
data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
```

### Module-level helper (for files with many reads)
```python
def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
```

### firebase_admin.auth edge
```python
def _get_user(uid: str) -> Any:
    return auth.get_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
```

### @firestore.transactional
```python
from google.cloud.firestore import transactional  # type: ignore[reportUnknownMemberType]
T = TypeVar("T")
def _typed_transactional(func: Callable[..., T]) -> Callable[..., T]:
    return transactional(func)  # type: ignore[reportUnknownMemberType]
```

### Decorator factory
```python
from functools import wraps
F = TypeVar("F", bound=Callable[..., Any])
def my_decorator(...) -> Callable[[F], F]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any: ...
    return cast(F, wrapper)
```

### Redis json.loads narrowing
```python
loaded: object = json.loads(raw_bytes)
data: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
```

### TypedDict document contract (for heavy files)
```python
class MemoryDoc(TypedDict, total=False):
    id: str
    uid: str
    ...
data = cast(MemoryDoc, _typed_doc(doc))
```

### deprecated datetime.utcnow() → datetime.now(timezone.utc)

### Common type fixes
- Unannotated function params: add type annotations (`param: str`, `param: Dict[str, Any]`, etc.)
- Missing return types: add `-> Dict[str, Any]`, `-> List[str]`, etc.
- `dict` without type args: `Dict[str, Any]` or specific TypedDict
- `list` without type args: `List[SpecificType]`
- `request.json()` returns `Any`: cast `loaded: object = request.json(); data = cast(Dict[str, Any], loaded)`
- Unused imports: remove them (reportUnusedImport is an error)
- `# type: ignore` must name the rule: `# type: ignore[reportUnknownMemberType]  # reason`

### After fixing a file
After achieving 0E/0W on a file, you do NOT need to update pyrightconfig.json,
pre-push, or type_safety.md — the coordinator (main agent) will do that in the
commit step. Just report the file is clean.

## Import Purity
Backend modules must be referentially transparent at import time. No constructing
clients, no network I/O, no `os.environ["X"]` at module scope. Use lazy getters.
