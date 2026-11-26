"""Wire the database snapshot reader to the shadow worker at service startup."""

from functools import partial

from database.firestore_document_probe import firestore_metrics_service_name
from database import firestore_snapshot_query
from database.monthly_usage_observation import install_monthly_usage_observer
from database.user_usage import read_hourly_usage_for_shadow
from utils.read_cache_shadow import compare_month


def install_month_shadow() -> None:
    fetch = partial(read_hourly_usage_for_shadow, stream_snapshot=firestore_snapshot_query.stream_at_read_time)
    install_monthly_usage_observer(partial(compare_month, fetch=fetch, service_name=firestore_metrics_service_name))
