# LIFECYCLE: permanent
"""Default-on structural optimizations; independent emergency kill switches."""

import os


def smart_merge_partition_enabled() -> bool:
    return os.getenv('FSR_SMART_MERGE_PARTITION', 'on').strip().lower() != 'off'


def kg_citation_index_enabled() -> bool:
    return os.getenv('FSR_KG_CITATION_INDEX', 'on').strip().lower() != 'off'


def public_catalog_cache_enabled() -> bool:
    return os.getenv('FSR_PUBLIC_CATALOG_CACHE', 'on').strip().lower() != 'off'


def cohort_request_cache_enabled() -> bool:
    return os.getenv('FSR_COHORT_REQUEST_CACHE', 'on').strip().lower() != 'off'
