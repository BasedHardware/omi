"""Postgres job-state store (workstream A): migrations, doc-mode `Store`, outbox.

Importing this package never imports the Postgres driver (``connection`` loads psycopg lazily), so
processes that do not select Postgres pay nothing.
"""

from importlib import import_module
from types import ModuleType
from typing import Any

# Lazy attributes are declared for type checkers; annotations do not bind them
# or execute their implementation imports at runtime.
DualStore: type[Any]
PostgresStore: type[Any]
connection: ModuleType
dual_store: ModuleType
migrate: ModuleType
outbox_pg: ModuleType
postgres_store: ModuleType

__all__ = ['DualStore', 'PostgresStore', 'connection', 'dual_store', 'migrate', 'outbox_pg', 'postgres_store']


def __getattr__(name):
    # A caller of a small authority/codec primitive must not import every store
    # and the entire enrichment dispatcher through outbox_pg. Preserve the public
    # package API, loading only the implementation the caller actually requests.
    classes = {'DualStore': 'dual_store', 'PostgresStore': 'postgres_store'}
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(f'{__name__}.{classes.get(name, name)}')
    value = getattr(module, name) if name in classes else module
    globals()[name] = value
    return value
