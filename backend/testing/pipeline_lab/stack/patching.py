"""Replace a function or class object in every loaded module namespace.

Product modules often ``from x import f``; patching ``x.f`` alone misses those
bound names. This walks ``sys.modules`` (as freezegun does for ``datetime``) and
swaps every module-level reference that *is* the original object, restoring each
one on exit. Only module ``__dict__`` entries are touched, never classes or
closures, so a reference captured inside a function default stays original.
"""

from __future__ import annotations

from contextlib import ExitStack
import sys
from typing import Any, Iterable

# Interpreter and test-runner machinery that must keep the real objects.
DEFAULT_SKIP_PREFIXES: tuple[str, ...] = (
    'threading',
    'queue',
    'multiprocessing',
    'concurrent',
    'asyncio',
    'selectors',
    '_pytest',
    'pytest',
    'pluggy',
    'unittest.mock',
    'testing.pipeline_lab.stack',
)


def _skipped(name: str, skip: Iterable[str]) -> bool:
    return any(name == prefix or name.startswith(prefix + '.') for prefix in skip)


def replace_everywhere(
    stack: ExitStack,
    original: Any,
    replacement: Any,
    *,
    skip_prefixes: Iterable[str] = DEFAULT_SKIP_PREFIXES,
    only_prefixes: Iterable[str] | None = None,
) -> int:
    """Swap ``original`` for ``replacement`` in loaded modules; return the count.

    ``only_prefixes`` limits the walk to those packages (e.g. product code only).
    """
    skip = tuple(skip_prefixes)
    only = tuple(only_prefixes) if only_prefixes is not None else None
    restored: list[tuple[dict, str]] = []
    for name, module in list(sys.modules.items()):
        if module is None or _skipped(name, skip):
            continue
        if only is not None and not _skipped(name, only):
            continue
        namespace = getattr(module, '__dict__', None)
        if not isinstance(namespace, dict):
            continue
        for attribute, value in list(namespace.items()):
            if value is original:
                namespace[attribute] = replacement
                restored.append((namespace, attribute))

    def restore() -> None:
        for namespace, attribute in restored:
            if namespace.get(attribute) is replacement:
                namespace[attribute] = original

    stack.callback(restore)
    return len(restored)


def replace_attribute_everywhere(
    stack: ExitStack, module_name: str, attribute: str, replacement: Any, *, import_module: bool = True
) -> int:
    """Resolve ``module_name.attribute`` and replace that object everywhere it is bound."""
    module = sys.modules.get(module_name)
    if module is None and import_module:
        import importlib

        module = importlib.import_module(module_name)
    if module is None or not hasattr(module, attribute):
        return 0
    return replace_everywhere(stack, getattr(module, attribute), replacement)
