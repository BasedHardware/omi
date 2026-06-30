import importlib
import json
from pathlib import Path

import pytest

from utils.memory.v3_archive_visibility_readiness import (
    decide_default_visibility,
    evaluate_archive_short_term_visibility_readiness,
)

ROOT = Path(__file__).resolve().parents[2]


def _ids(records):
    return [record['memory_id'] for record in records if record['default_visible']]


def test_default_visibility_excludes_archive_and_stale_short_term_by_default():
    records = [
        {
            'memory_id': 'archive_general',
            'memory_layer': 'l1_archive',
            'archive_class': 'general',
            'visibility': 'archived_evidence',
            'source_freshness': 'historical',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'short_stale',
            'memory_layer': 'working',
            'lifecycle_status': 'working',
            'visibility': 'short_term',
            'source_freshness': 'stale',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'short_fresh',
            'memory_layer': 'working',
            'lifecycle_status': 'working',
            'visibility': 'short_term',
            'source_freshness': 'fresh',
            'source_backed_projection': True,
        },
        {
            'memory_id': 'durable_active',
            'memory_layer': 'durable',
            'lifecycle_status': 'active',
            'visibility': 'long_term',
            'source_freshness': 'stable',
            'source_backed_projection': True,
        },
    ]

    evaluated = [decide_default_visibility(record) for record in records]

    assert _ids(evaluated) == ['short_fresh', 'durable_active']
    assert evaluated[0]['reason'] == 'archive_requires_explicit_opt_in'
    assert evaluated[1]['reason'] == 'stale_short_term_requires_explicit_opt_in'
    assert evaluated[2]['agent_use'] == 'fresh_short_term_source_backed_context'
    assert evaluated[3]['agent_use'] == 'stable_profile_fact'


def test_explicit_archive_historical_opt_in_does_not_make_archive_default_visible():
    archive = {
        'memory_id': 'archive_general',
        'memory_layer': 'l1_archive',
        'archive_class': 'general',
        'visibility': 'archived_evidence',
        'source_freshness': 'historical',
        'source_backed_projection': True,
    }

    default_decision = decide_default_visibility(archive)
    request_only_decision = decide_default_visibility(archive, include_archive=True, include_historical=True)
    opt_in_decision = decide_default_visibility(
        archive,
        include_archive=True,
        include_historical=True,
        server_archive_capability=True,
        server_historical_capability=True,
    )

    assert default_decision['default_visible'] is False
    assert request_only_decision['opt_in_visible'] is False
    assert request_only_decision['reason'] == 'archive_requires_server_capability'
    assert opt_in_decision['default_visible'] is False
    assert opt_in_decision['opt_in_visible'] is True
    assert opt_in_decision['reason'] == 'archive_visible_only_by_explicit_opt_in'


def test_fresh_short_term_requires_explicit_approved_working_lifecycle_before_default_visible():
    base = {
        'memory_id': 'short_missing_lifecycle',
        'memory_layer': 'working',
        'visibility': 'short_term',
        'source_freshness': 'fresh',
        'source_backed_projection': True,
    }

    missing_lifecycle = decide_default_visibility(base)
    review_lifecycle = decide_default_visibility({**base, 'lifecycle_status': 'review'})
    working_lifecycle = decide_default_visibility({**base, 'lifecycle_status': 'working'})

    assert missing_lifecycle['default_visible'] is False
    assert missing_lifecycle['reason'] == 'short_term_requires_approved_working_lifecycle'
    assert review_lifecycle['default_visible'] is False
    assert review_lifecycle['reason'] == 'short_term_requires_approved_working_lifecycle'
    assert working_lifecycle['default_visible'] is True


@pytest.mark.parametrize(
    'record, reason',
    [
        (
            {
                'memory_id': 'unknown_visibility',
                'memory_layer': 'working',
                'visibility': 'mystery',
                'source_freshness': 'fresh',
                'source_backed_projection': True,
            },
            'unknown_visibility_fail_closed',
        ),
        (
            {
                'memory_id': 'unknown_lifecycle',
                'memory_layer': 'durable',
                'visibility': 'long_term',
                'lifecycle_status': 'weird',
                'source_freshness': 'stable',
                'source_backed_projection': True,
            },
            'unknown_lifecycle_fail_closed',
        ),
        (
            {
                'memory_id': 'unknown_freshness',
                'memory_layer': 'working',
                'visibility': 'short_term',
                'lifecycle_status': 'working',
                'source_freshness': 'unknown',
                'source_backed_projection': True,
            },
            'unknown_source_freshness_fail_closed',
        ),
        (
            {
                'memory_id': 'unbacked_short',
                'memory_layer': 'working',
                'visibility': 'short_term',
                'lifecycle_status': 'working',
                'source_freshness': 'fresh',
                'source_backed_projection': False,
            },
            'short_term_requires_source_backed_projection',
        ),
    ],
)
def test_visibility_contract_fails_closed_on_unknown_or_unbacked_inputs(record, reason):
    decision = decide_default_visibility(record)

    assert decision['default_visible'] is False
    assert decision['opt_in_visible'] is False
    assert decision['reason'] == reason


def test_readiness_report_is_blocked_read_only_and_sanitized():
    report = evaluate_archive_short_term_visibility_readiness(
        sample_records=[
            {
                'memory_id': 'secret_user_text_must_not_leak',
                'memory_layer': 'l1_archive',
                'archive_class': 'general',
                'visibility': 'archived_evidence',
                'source_freshness': 'historical',
                'source_backed_projection': True,
                'content': 'raw user content should not be logged',
                'cursor': 'cursor_secret',
                'api_key': 'sk-secret',
            }
        ]
    )

    encoded = json.dumps(report, sort_keys=True)
    assert report['status'] == 'BLOCKED'
    assert report['approval'] is False
    assert report['read_only'] is True
    assert report['route_wiring'] is False
    assert report['production_call_count'] == 0
    assert report['firestore_write_count'] == 0
    assert report['telemetry_sink_call_count'] == 0
    assert report['provider_or_vector_call_count'] == 0
    assert report['legacy_fallback_or_merge'] is False
    assert 'raw user content' not in encoded
    assert 'cursor_secret' not in encoded
    assert 'sk-secret' not in encoded
    assert 'secret_user_text_must_not_leak' not in encoded
    assert 'default_visible_ids' not in report
    assert 'blocked_or_opt_in_required_ids' not in report
    assert report['summary']['default_visible_count'] == 0
    assert report['summary']['archive_opt_in_required_count'] == 1
    assert all('memory_id' not in decision for decision in report['decisions'])


def test_readiness_module_and_script_do_not_import_memories_router():
    import sys

    sys.modules.pop('routers.memories', None)
    importlib.import_module('utils.memory.v3_archive_visibility_readiness')
    importlib.import_module('scripts.p1_3_v3_archive_short_term_visibility_readiness')

    script_source = (ROOT / 'scripts' / 'p1_3_v3_archive_short_term_visibility_readiness.py').read_text()
    utility_source = (ROOT / 'utils' / 'memory' / 'v3_archive_visibility_readiness.py').read_text()
    assert 'routers.memories' not in sys.modules
    assert 'routers.memories' not in script_source
    assert 'routers.memories' not in utility_source
