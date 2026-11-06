"""Registration seam for domain adapters supplied by the A lanes.

Registries are explicit objects owned by composition, never import-time global
state. Factories receive a CellTransaction and return the domain-typed view.
"""

from typing import Callable, Generic, TypeVar

from database.cells.store import CellTransaction

T = TypeVar('T')


class AdapterRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[CellTransaction], T]] = {}

    def register(self, domain: str, factory: Callable[[CellTransaction], T]) -> None:
        if domain in self._factories:
            raise ValueError('domain adapter already registered')
        self._factories[domain] = factory

    def bind(self, domain: str, transaction: CellTransaction) -> T:
        return self._factories[domain](transaction)
