#!/usr/bin/env python3
"""Warm tiktoken's cache with bounded retry for transient upstream outages."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def _retryable(error: Exception) -> bool:
    """Return whether a failed tokenizer download is plausibly transient."""
    response = getattr(error, 'response', None)
    status_code = getattr(response, 'status_code', None)
    return status_code == 429 or (isinstance(status_code, int) and 500 <= status_code < 600)


def prewarm(
    load_encoding: Callable[[str], Any],
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Load cl100k_base from the configured cache, retrying only transient HTTP failures."""
    for attempt in range(1, attempts + 1):
        try:
            load_encoding('gpt-4')
            print(f'tiktoken cl100k_base cache is ready (attempt {attempt}/{attempts}).')
            return
        except Exception as error:
            if attempt == attempts or not _retryable(error):
                raise RuntimeError(
                    f'tiktoken prewarm failed on attempt {attempt}/{attempts}: ' f'{type(error).__name__}: {error}'
                ) from error
            delay = float(attempt)
            print(
                f'tiktoken prewarm transient failure on attempt {attempt}/{attempts}: '
                f'{type(error).__name__}: {error}; retrying in {delay:.0f}s.',
                flush=True,
            )
            sleep(delay)


def main() -> int:
    try:
        import tiktoken

        prewarm(tiktoken.encoding_for_model)
    except Exception as error:
        print(f'ERROR: {error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
