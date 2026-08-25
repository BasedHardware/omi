# Backend Type Safety

Backend Python type checking uses Pyright in strict mode with `reportUnknown*`
rules at warning level. This is a **global policy** — every production backend
`.py` file is enrolled; the typecheck must report **0 errors, 0 warnings**.

## Run It

```bash
cd backend
bash scripts/typecheck.sh
```

The script runs `python -m pyright` with `backend/pyrightconfig.json`, analyzes
with Python 3.11 on Linux in strict mode, and treats warnings as failures.

## Coverage

`pyrightconfig.json` uses **directory-level includes** for all production code:

| Package | Description |
|---------|-------------|
| `database/` | Firestore/Redis adapters with TypedDict contracts |
| `models/` | Pydantic models, TypedDicts, enums |
| `routers/` | FastAPI endpoints |
| `utils/` | Business logic, LLM clients, STT, memory, retrieval |
| `config/` | Runtime configuration |
| `services/` | Service-layer helpers |
| `jobs/` | Background job definitions |
| `llm_gateway/` | Internal LLM gateway service |
| `pusher/` | Audio push WebSocket service |
| `agent-proxy/` | Agent VM WebSocket proxy |
| `parakeet/` | GPU STT service |
| `diarizer/` | Speaker embedding service |
| `modal/` | VAD + speech profile service |
| `main.py` | FastAPI app entry point |

Selected non-throwaway scripts are enrolled individually. Benchmark/test scripts
in `scripts/stt/`, `scripts/rag/`, `scripts/chat/` etc. are not enrolled.

## Policy For New Backend Code

- Public functions **must** annotate parameters and return values.
- Runtime config loaded from YAML/JSON should cross a typed boundary: Pydantic
  models, dataclasses, or `TypedDict`.
- Treat dynamic input as `object` at the boundary, validate its shape, then cast
  to the narrow type after checks.
- Avoid broad `Any`; when unavoidable, keep it local to the edge that receives
  untyped third-party data.
- `# type: ignore` comments must name the rule and include a short reason.

## Edge-Adapter Patterns

### Firestore read (most common)

```python
raw: object = doc.to_dict()
data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
```

Module-level helper for files with many reads:

```python
def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
```

### firebase_admin.auth

```python
def _get_user(uid: str) -> Any:
    return auth.get_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
```

### Redis json.loads

```python
loaded: object = json.loads(raw_bytes)
data: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
```

### TypedDict document contract (heavy traffic)

```python
class MemoryDoc(TypedDict, total=False):
    id: str
    uid: str
    # ...

data = cast(MemoryDoc, _typed_doc(doc))
```

### Decorator factory

```python
F = TypeVar("F", bound=Callable[..., Any])
def my_decorator(...) -> Callable[[F], F]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any: ...
    return cast(F, wrapper)
```

### deprecated datetime.utcnow()

Use `datetime.now(timezone.utc)` instead.

## Pre-push Gate

The `scripts/pre-push` hook runs `bash scripts/typecheck.sh` whenever any
`backend/**/*.py` file, `pyrightconfig.json`, `typecheck.sh`, `requirements.txt`,
or `pylock*.toml` changes. Skip with `PRE_PUSH_SKIP_BACKEND_TYPECHECK=1`.
