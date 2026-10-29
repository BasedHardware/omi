"""Synthetic metadata queries; real builders/indexes have separate guards. No IO."""

from copy import deepcopy
from types import SimpleNamespace


class MetadataQuery:
    """Synthetic metadata query fixture; query/index shapes have their own real-builder guard."""

    def __init__(self, rows, filters=(), limit=None):
        self.rows, self.filters, self.bound = rows, filters, limit

    def where(self, field, op, value):
        return MetadataQuery(self.rows, (*self.filters, (field, op, value)), self.bound)

    def order_by(self, field):
        return self

    def select(self, fields):
        return self

    def limit(self, value):
        return MetadataQuery(self.rows, self.filters, value)

    def stream(self):
        matches = []
        for row in self.rows:
            for field, op, value in self.filters:
                actual = row.get(field)
                if actual is None or not (
                    actual == value if op == '==' else actual <= value if op == '<=' else actual > value
                ):
                    break
            else:
                matches.append(SimpleNamespace(to_dict=lambda row=row: deepcopy(row)))
        return iter(matches[: self.bound])


def metadata_client(rows):
    return SimpleNamespace(collection=lambda name: MetadataQuery(rows))
