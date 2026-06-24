from __future__ import annotations

from scripts.v3_get_runtime_snapshot_readiness import build_report


def test_runtime_snapshot_readiness_report_remains_blocked_and_sanitized():
    report = build_report(execute=True)

    assert report['status'] == 'BLOCKED'
    assert report['proof_status'] == 'BLOCKED'
    assert report['approval'] is False
    assert report['route_wiring'] is False
    assert report['runtime_behavior_changed'] is False
    assert report['production_call_count'] == 0
    assert report['firestore_write_count'] == 0
    assert report['network_call_count'] == 0
    assert report['telemetry_sink_call_count'] == 0
    assert report['provider_or_vector_call_count'] == 0
    assert report['reason_counts']['snapshot_coherent'] == 1
    assert report['reason_counts']['generation_mismatch'] == 1
    assert report['reason_counts']['malformed_source_output'] == 1
    rendered = repr(report)
    assert 'sample-subject' not in rendered
    assert 'present' not in rendered
    assert "'cursor_secret_version': 'present'" not in rendered
