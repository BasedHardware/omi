"""Synthetic metadata queries; real builders/indexes have separate guards. No IO."""

from copy import deepcopy
from types import SimpleNamespace


class MetadataQuery:
    """Synthetic metadata query fixture; query/index shapes have their own real-builder guard."""

    def __init__(self, rows, filters=(), limit=None, projection=None):
        self.rows, self.filters, self.bound, self.projection = rows, filters, limit, projection

    def where(self, field, op, value):
        return MetadataQuery(self.rows, (*self.filters, (field, op, value)), self.bound, self.projection)

    def order_by(self, field):
        return self

    def select(self, fields):
        return MetadataQuery(self.rows, self.filters, self.bound, tuple(fields))

    def limit(self, value):
        return MetadataQuery(self.rows, self.filters, value, self.projection)

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
                projected = deepcopy(row)
                if self.projection is not None:
                    projected = {}
                    for path in self.projection:
                        source, target = row, projected
                        parts = path.split('.')
                        for part in parts[:-1]:
                            source = source.get(part, {})
                            if not isinstance(source, dict):
                                break
                            target = target.setdefault(part, {})
                        else:
                            if parts[-1] in source:
                                target[parts[-1]] = deepcopy(source[parts[-1]])
                matches.append(SimpleNamespace(to_dict=lambda row=projected: deepcopy(row)))
        return iter(matches[: self.bound])


def metadata_client(rows):
    return SimpleNamespace(collection=lambda name: MetadataQuery(rows))
