"""Content-addressed private eval receipts and output-path guards."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from testing.episode_notes.schema import LLMResult, _result


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
) -> LLMResult:
    key = fingerprint({'model': model, 'prompt': prompt, 'payload': payload})
    path = directory / f'{kind}-{key}.json' if directory else None
    if path is not None and path.exists():
        receipt = json.loads(path.read_text())
        if receipt.get('key') == key:
            return LLMResult(**receipt['result'])
    result = _result(llm(prompt, payload))
    if path is not None:
        write_json(path, {'key': key, 'result': {'content': result.content, **result.cost()}})
    return result
