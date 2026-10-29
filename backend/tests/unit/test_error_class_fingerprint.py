"""Error-class fingerprint normalizer contracts."""

import json

from utils.error_class_fingerprint import (
    entry_logger,
    entry_text,
    extract_exception,
    extract_site,
    fingerprint_entry,
    normalize,
    stitch_tracebacks,
)


def cr_entry(text, service='backend-sync', pod=None):
    labels = {'service_name': service}
    return {
        'textPayload': text,
        'resource': {'type': 'cloud_run_revision', 'labels': labels},
        'logName': 'projects/based-hardware/logs/run.googleapis.com%2Fstdout',
    }


def k8s_entry(text, pod='prod-batch-pipeline-worker-abc'):
    labels = {'pod_name': pod, 'cluster_name': 'prod-omi-gke', 'container_name': 'worker'}
    return {
        'textPayload': text,
        'resource': {'type': 'k8s_container', 'labels': labels},
        'logName': 'projects/based-hardware/logs/stderr',
    }


def test_normalize_replaces_every_id_like_token_family():
    raw = (
        "user 3f2a8b12-9c4d-4e5f-8a7b-1c2d3e4f5a6b at 10.0.1.23 mail a@b.co "
        "hex deadbeefcafe1234 num 4711 slug zzsec3005c471789 'quoted' \"dq\" v2.1"
    )
    out = normalize(raw)
    for token in ('<uid>', '<ip>', '<email>', '<hex>', '<n>', '<id>', '<q>'):
        assert token in out, token
    for token in ('3f2a8b12', '10.0.1.23', 'a@b.co', 'deadbeefcafe1234', '4711', 'zzsec3005', 'quoted'):
        assert token not in out, token


def test_normalize_keeps_words_without_long_digit_runs():
    assert normalize('batch_policy_kill_switch api36 429') == 'batch_policy_kill_switch api36 <n>'


def test_level_and_logger_parse_both_log_formats():
    a = fingerprint_entry(k8s_entry('WARNING utils.apps: Skipping malformed marketplace app zzsec3005c4717'))
    assert a.level == 'WARNING'
    assert a.fingerprint.startswith('WARNING|Skipping malformed marketplace app <id>|utils.apps')

    b = fingerprint_entry(
        k8s_entry('INFO:config.policy.kill_switches:event=batch_policy_kill_switch policy_id=control')
    )
    assert b.level == 'INFO'
    assert 'config.policy.kill_switches' in b.fingerprint


def test_exception_fingerprint_uses_innermost_site():
    text = (
        'ERROR services.batch: job failed\n'
        'Traceback (most recent call last):\n'
        '  File "/app/services/batch.py", line 10, in run\n'
        '  File "/app/utils/contracts.py", line 45, in check\n'
        'ValueError: VAD span end before start for 12345'
    )
    fp = fingerprint_entry({'textPayload': text, 'resource': {'labels': {}}, 'logName': 'x/stderr'})
    assert fp.exception == 'ValueError'
    assert fp.fingerprint == 'ValueError|contracts.py:45|services.batch'
    assert fp.level == 'ERROR'


def test_warning_exception_keeps_warning_level_for_thresholds():
    text = 'WARNING routers.y: bad thing\nValueError: nope'
    fp = fingerprint_entry({'textPayload': text, 'resource': {'labels': {}}, 'logName': 's'})
    assert fp.exception == 'ValueError'
    assert fp.level == 'WARNING'


def test_extract_exception_takes_the_last_exception_line():
    text = 'During handling: RuntimeError: cause\nValueError: real one'
    assert extract_exception(text) == 'ValueError'


def test_extract_site_prefers_frames_then_site_field_then_inline_location():
    assert extract_site('  File "/a/b/x.py", line 3, in f\n  File "/a/y.py", line 9, in g') == 'y.py:9'
    assert extract_site('event=discard site=routers.sync:221 type=Error') == 'routers.sync:221'
    assert extract_site('failed at contracts.py:45 badly') == 'contracts.py:45'


def test_site_from_json_payload_field():
    entry = {'jsonPayload': {'message': 'job blew up', 'site': 'worker.py:88'}, 'resource': {'labels': {}}}
    assert extract_site(entry_text(entry), entry['jsonPayload']) == 'worker.py:88'


def test_request_log_errors_fingerprint_on_status_and_path():
    entry = {
        'protoPayload': {
            'statusMessage': 'Internal error',
            'requestUrl': 'https://api.omi.me/v1/conversations/3f2a8b12-9c4d-4e5f-8a7b-1c2d3e4f5a6b/posts?x=1',
        },
        'resource': {'labels': {}},
        'logName': 'x',
    }
    fp = fingerprint_entry(entry)
    assert 'Internal error' in fp.fingerprint
    assert 'url /v1/conversations/<uid>/posts' in fp.fingerprint


def test_stitch_tracebacks_merges_block_into_one_entry():
    lines = [
        k8s_entry('INFO keepalive tick'),
        k8s_entry('Traceback (most recent call last):'),
        k8s_entry('  File "/app/utils/contracts.py", line 45, in check'),
        k8s_entry('ValueError: bad span 99'),
        k8s_entry('INFO after'),
    ]
    stitched = stitch_tracebacks(lines)
    texts = [e['textPayload'] for e in stitched]
    assert len(stitched) == 3
    assert '\n' in texts[1] and 'contracts.py' in texts[1] and 'ValueError:' in texts[1]
    fp = fingerprint_entry(stitched[1])
    assert fp.fingerprint == 'ValueError|contracts.py:45|stderr'


def test_stitch_tracebacks_flushes_broken_block_and_keeps_unrelated_lines():
    lines = [
        k8s_entry('Traceback (most recent call last):'),
        k8s_entry('  File "/app/a.py", line 1, in f'),
        k8s_entry('WARNING unrelated logger: noise'),
    ]
    stitched = stitch_tracebacks(lines)
    assert len(stitched) == 2
    assert 'WARNING unrelated' in stitched[1]['textPayload']
    assert stitched[0]['textPayload'].startswith('Traceback')


def test_entry_logger_unquotes_logname_and_prefers_payload_logger():
    assert entry_logger({'logName': 'projects/p/logs/run.googleapis.com%2Fstderr'}) == 'stderr'
    assert entry_logger({'logName': 'projects/p/logs/stdout', 'jsonPayload': {'logger': 'utils.x'}}) == 'utils.x'


def test_same_class_different_ids_share_fingerprint():
    a = fingerprint_entry(k8s_entry("WARNING routers.pusher: Durable audio projection failure for 12345"))
    b = fingerprint_entry(k8s_entry("WARNING routers.pusher: Durable audio projection failure for 98765"))
    assert a.fingerprint == b.fingerprint


def test_distinct_sites_stay_distinct_classes():
    a = fingerprint_entry(
        {'textPayload': 'ValueError: x at contracts.py:45', 'resource': {'labels': {}}, 'logName': 's'}
    )
    b = fingerprint_entry(
        {'textPayload': 'ValueError: x at contracts.py:52', 'resource': {'labels': {}}, 'logName': 's'}
    )
    assert a.fingerprint != b.fingerprint


def test_fingerprint_payload_never_carries_raw_ids():
    fp = fingerprint_entry(k8s_entry('ERROR db.users: load failed for 3f2a8b12-9c4d-4e5f-8a7b-1c2d3e4f5a6b'))
    assert '3f2a8b12' not in fp.fingerprint
    assert '3f2a8b12' not in fp.label
    assert '<uid>' in fp.fingerprint


def test_entry_source_key_groups_by_resource_labels_only():
    a = cr_entry('x')
    b = cr_entry('y')
    c = k8s_entry('z')
    assert a and b and c
    assert json.loads(json.dumps({'service_name': 'backend-sync'})) == {'service_name': 'backend-sync'}
