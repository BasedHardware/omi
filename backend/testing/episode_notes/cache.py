"""Content-addressed private eval receipts and output-path guards."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from testing.episode_notes.schema import LLMCallError, LLMResult, _result


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_output_path(path: Path, *, synthetic: bool) -> None:
    if synthetic:
        return
    resolved = path.expanduser().resolve()
    if any((parent / '.git').exists() for parent in (resolved, *resolved.parents)):
        raise ValueError('non-synthetic output and caches must be outside every git worktree')


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Atomic replace prevents interrupted runs from leaving unusable cache entries.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
            handle.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def cached_call(
    directory: Path | None,
    kind: str,
    model: str,
    prompt: str,
    payload: dict,
    llm: Callable[[str, dict], dict | LLMResult],
    validate: Callable[[dict], object] | None = None,
) -> LLMResult:
    prepare = getattr(llm, 'prepare_payload', None)
    if prepare is not None:
        payload = prepare(prompt, payload)
    key = fingerprint({'model': model, 'prompt': prompt, 'payload': payload})
    path = directory / f'{kind}-{key}.json' if directory else None
    if path is not None and path.exists():
        receipt = json.loads(path.read_text())
        if receipt.get('key') == key:
            cached = LLMResult(**receipt['result'])
            try:
                if validate is not None:
                    validate(cached.content)
            except Exception:
                pass  # Older invalid receipts must not poison a resumed judge call.
            else:
                return cached
    result = _result(llm(prompt, payload))
    if validate is not None:
        try:
            validate(result.content)
        except Exception as exc:
            raise LLMCallError(
                type(exc).__name__,
                LLMResult(
                    content={},
                    **result.cost(),
                    finish_reason=result.finish_reason,
                    effective_effort=result.effective_effort,
                ),
            ) from None
    if path is not None:
        write_json(
            path,
            {
                'key': key,
                'result': {
                    'content': result.content,
                    **result.cost(),
                    'finish_reason': result.finish_reason,
                    'effective_effort': result.effective_effort,
                },
            },
        )
    return result
