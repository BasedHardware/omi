"""Database-side observation hook. Serving processes install the shadow worker."""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any


class ShadowSkipped(Exception):
    """A bounded shadow read cannot produce a complete comparable value."""


Observer = Callable[[str, str, datetime, datetime | None, dict, Any, Any, str | None], None]
_observer: Observer | None = None


def install_monthly_usage_observer(observer: Observer) -> None:
    global _observer
    _observer = observer


def observe_monthly_usage(
    path: str,
    uid: str,
    date: datetime,
    start_date: datetime | None,
    served: dict,
    client: Any,
    read_time: Any,
    epoch: str | None,
) -> None:
    observer = _observer
    if observer is not None:
        try:
            observer(path, uid, date, start_date, served, client, read_time, epoch)
        except Exception:
            pass  # Observations cannot change the value served by a reader.


def observe_cached_month(uid, date, start_date, served, client, metadata):
    source = metadata if isinstance(metadata, Mapping) else {}
    observe_monthly_usage(
        'cache_hit', uid, date, start_date, served, client, source.get('read_time'), source.get('epoch')
    )
