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
    token: str = 'gpt-4',
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Load ``token`` from the configured cache, retrying only transient HTTP failures.

    ``token`` is whatever ``load_encoding`` expects — a model name for
    ``tiktoken.encoding_for_model`` (default ``'gpt-4'`` → cl100k_base) or an encoding name for
    ``tiktoken.get_encoding`` (e.g. ``'o200k_base'``)."""
    for attempt in range(1, attempts + 1):
        try:
            load_encoding(token)
            print(f'tiktoken {token} cache is ready (attempt {attempt}/{attempts}).')
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


# The encodings the backend actually requests at runtime (utils/llm/clients.py `encoding_for_model`
# -> cl100k_base; utils/llm/conversation_processing.py `get_encoding('o200k_base')`). Baking exactly
# these keeps the no-egress on-prem runtime from fetching them on first use.
BAKED_ENCODINGS: tuple[str, ...] = ('cl100k_base', 'o200k_base')


def main(encodings: tuple[str, ...] = BAKED_ENCODINGS) -> int:
    try:
        import tiktoken

        for encoding in encodings:
            prewarm(tiktoken.get_encoding, token=encoding)
    except Exception as error:
        print(f'ERROR: {error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    import sys

    raise SystemExit(main(tuple(sys.argv[1:]) or BAKED_ENCODINGS))
