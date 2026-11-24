"""Ordered union of disjoint category queries for external conversation lists."""

from contextlib import closing
from dataclasses import dataclass, replace
from heapq import merge
from itertools import islice
from typing import Any

from google.api_core.datetime_helpers import DatetimeWithNanoseconds, to_microseconds

from utils.other.list_budget import budgeted_stream_iter


def category_batches(categories, statuses, *, extra_filters=0):
    """Fit each query within Firestore's 100 DNF terms and 30 disjunctions.

    Reserve terms per disjunct for the category, status, discarded flag, both
    date bounds, both sort keys, and the user's parent document path.
    """
    values = list(dict.fromkeys(categories or ()))
    status_count = max(1, len(statuses))
    width = min(30, 100 // (8 + extra_filters)) // status_count
    return [values[start : start + width] for start in range(0, len(values), width)] or [[]]


@dataclass(frozen=True)
class PartitionedConversationQuery:
    queries: tuple[Any, ...]
    window_size: int | None = None
    skip: int = 0

    def order_by(self, *args, **kwargs):
        return replace(self, queries=tuple(query.order_by(*args, **kwargs) for query in self.queries))

    def select(self, fields):
        return replace(self, queries=tuple(query.select(fields) for query in self.queries))

    def start_after(self, bookmark):
        return replace(self, queries=tuple(query.start_after(bookmark) for query in self.queries))

    def offset(self, count):
        return replace(self, skip=count)

    def limit(self, count):
        return replace(self, window_size=count)

    def iter_documents(self, budget=None):
        queries = self.queries
        if self.skip:
            # Locate the raw offset using ordering keys only. In particular,
            # developer transcript pages should never download skipped text.
            keys = tuple(query.select(['created_at']) for query in queries)
            with closing(_merge_windows(keys, self.skip, budget)) as merged:
                bookmark = next(islice(merged, self.skip - 1, self.skip), None)
            if bookmark is None:
                return
            queries = tuple(query.start_after(bookmark) for query in queries)
        with closing(_merge_windows(queries, self.window_size, budget)) as merged:
            yield from islice(merged, self.window_size)


def _merge_windows(queries, size, budget):
    streams = [
        iter(budgeted_stream_iter(query.limit(size) if size is not None else query, budget)) for query in queries
    ]
    try:
        yield from merge(*streams, key=_position, reverse=True)
    finally:
        for stream in streams:
            stream.close()


def combine_category_queries(queries):
    queries = tuple(queries)
    return queries[0] if len(queries) == 1 else PartitionedConversationQuery(queries)


def _position(doc):
    stamp = doc.get('created_at')
    if stamp is None:
        return float('-inf'), 0, doc.id
    seconds, micros = divmod(to_microseconds(stamp), 1_000_000)
    nanos = stamp.nanosecond if isinstance(stamp, DatetimeWithNanoseconds) else 0
    nanos = nanos or micros * 1_000
    return seconds, nanos, doc.id
