"""Registration seam for domain adapters supplied by the A lanes.

Registries are explicit objects owned by composition, never import-time global
state. Factories receive a CellTransaction and return the domain-typed view.
"""

from importlib import import_module
from typing import Any, Callable, Generic, TypeVar, TYPE_CHECKING

from database.cells.store import CellTransaction

if TYPE_CHECKING:
    from database.cells.adapters.space_store import CellSpaceStore as CellSpaceStore

__all__ = ['AdapterRegistry', 'CellSpaceStore']

T = TypeVar('T')


def __getattr__(name: str) -> Any:
    # The public composition entry point is lazy: importing the low-level cell
    # store must not import domain dependencies or create connection pools.
    if name == 'CellSpaceStore':
        return import_module('database.cells.adapters.space_store').CellSpaceStore
    raise AttributeError(name)


class AdapterRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[CellTransaction], T]] = {}

    def register(self, domain: str, factory: Callable[[CellTransaction], T]) -> None:
        if domain in self._factories:
            raise ValueError('domain adapter already registered')
        self._factories[domain] = factory

    def bind(self, domain: str, transaction: CellTransaction) -> T:
        return self._factories[domain](transaction)
