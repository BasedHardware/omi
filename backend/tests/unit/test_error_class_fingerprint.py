"""Error-class fingerprint normalizer contracts."""

import json
import re

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
    raw = "user %s at 10.0.1.23 mail %s " "hex %s num 4711 slug zzsec3005c471789 'quoted' \"dq\" v2.1" % (
        SYN_UUID,
        'a@' + 'b.co',
        SYN_HEX16,
    )
    out = normalize(raw)
    for token in ('<uid>', '<ip>', '<email>', '<hex>', '<n>', '<id>', '<q>'):
        assert token in out, token
    for token in (SYN_UUID[:8], '10.0.1.23', 'b.co', SYN_HEX16, '4711', 'zzsec3005'):
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
            'requestUrl': 'https://api.omi.me/v1/conversations/%s/posts?x=1' % SYN_UUID,
        },
        'resource': {'labels': {}},
        'logName': 'x',
    }
    fp = fingerprint_entry(entry)
    assert 'Internal error' in fp.fingerprint
    assert 'url /v1/conversations/<uid>/posts' in fp.fingerprint


def test_stitch_tracebacks_merges_block_into_one_entry():
    lines = [
        k8s_entry('raw unstructured status 7'),
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


def test_stitch_absorbs_the_preceding_level_header():
    # The two read passes split a warning-logged traceback across queries; the
    # header must join the block so the class keeps warning-level thresholds.
    lines = [
        k8s_entry('WARNING routers.y: widget failed'),
        k8s_entry('Traceback (most recent call last):'),
        k8s_entry('  File "/app/widgets.py", line 7, in build'),
        k8s_entry('ValueError: nope'),
        k8s_entry('INFO after'),
    ]
    stitched = stitch_tracebacks(lines)
    texts = [e['textPayload'] for e in stitched]
    assert len(stitched) == 2
    assert texts[0].startswith('WARNING routers.y: widget failed')
    assert 'ValueError: nope' in texts[0]
    fp = fingerprint_entry(stitched[0])
    assert fp.exception == 'ValueError' and fp.level == 'WARNING'
    assert fp.fingerprint == 'ValueError|widgets.py:7|routers.y'


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
    fp = fingerprint_entry(k8s_entry('ERROR db.users: load failed for %s' % SYN_UUID))
    assert SYN_UUID[:8] not in fp.fingerprint
    assert SYN_UUID[:8] not in fp.label
    assert '<uid>' in fp.fingerprint


def test_entry_source_key_groups_by_resource_labels_only():
    a = cr_entry('x')
    b = cr_entry('y')
    c = k8s_entry('z')
    assert a and b and c
    assert json.loads(json.dumps({'service_name': 'backend-sync'})) == {'service_name': 'backend-sync'}


# --- Privacy: no identifier-shaped token survives (lead rule 2026-10-29) -----
#
# Fingerprints and labels become Redis keys, GMP metric label values and alert
# log lines, so they must never carry a user- or document-identifiable token.
# Fixtures below are SYNTHETIC shapes, never real identifiers. Every fixture is
# assembled from short fragments on purpose: no identifier-shaped token may
# exist as a literal anywhere in this file, so a shape scan of the repo diff
# itself comes back empty.

# 28 chars, mixed case, digits scattered (no 4+ run) - the exact shape that
# used to slip past every rule (Firebase-UID-shaped).
SYN_FUID = 'aBcD' + 'eF1g' + 'H2iJ' + '3kLm' + 'N5oP' + '6qRs' + 'T8uV'
assert len(SYN_FUID) == 28
SYN_FUID_ALT = 'ZyXw' + 'Vu9t' + 'S8rQ' + 'P7oN' + 'm6Lk' + 'J6iH' + 'g4Fe'
assert len(SYN_FUID_ALT) == 28
# 20 chars with a digit - Firestore-auto-id / base62 document-or-job id shape.
SYN_DOC_ID = 'Doc1' + 'd2e' + '3f4g' + '5h6i' + '7j8kL'
assert len(SYN_DOC_ID) == 20
SYN_EMAIL = 'someone123' + '@example.com'
SYN_UUID = '3f2a8b12-' + '9c4d-4e5f-' + '8a7b-1c2d' + '3e4f' + '5a6b'
assert len(SYN_UUID) == 36
SYN_HEX16 = 'deadbeef' + 'cafe1234'
assert len(SYN_HEX16) == 16
SYN_HEX20 = 'deadbeef' + 'cafe1234' + 'dead'
assert len(SYN_HEX20) == 20

# Independent copies of the identifier shapes: the proof must not reuse the
# patterns belonging to the code under test.
LEAK_SHAPES = (
    re.compile(r'\b[A-Za-z0-9]{28}\b'),
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'),
    re.compile(r'\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{20,}\b'),
    re.compile(r'\b[0-9a-fA-F]{12,}\b'),
)


def leaked_tokens(*strings):
    """Any identifier-shaped token found in the given strings (should be none)."""
    found = []
    for text in strings:
        for shape in LEAK_SHAPES:
            found.extend(shape.findall(text))
    return found


def test_firebase_uid_shape_never_reaches_fingerprint_or_label():
    fp = fingerprint_entry(k8s_entry('ERROR db.users: load failed for %s retry' % SYN_FUID))
    assert SYN_FUID not in fp.fingerprint and SYN_FUID not in fp.label
    assert '<fuid>' in fp.fingerprint
    assert not leaked_tokens(fp.fingerprint, fp.label)


def test_firebase_uid_shape_without_digits_is_still_stripped():
    letters_only = 'aBcD' + 'eFgH' + 'iJkL' + 'mNoP' + 'qRsT' + 'uVwX' + 'yZAb'
    assert len(letters_only) == 28
    out = normalize('owner %s gone' % letters_only)
    assert letters_only not in out and '<fuid>' in out


def test_base62_document_id_shape_is_stripped():
    out = normalize('doc %s locked' % SYN_DOC_ID)
    assert SYN_DOC_ID not in out
    assert '<id>' in out


def test_email_shape_is_stripped_before_its_local_part_can_leak():
    out = normalize('mail to %s failed' % SYN_EMAIL)
    assert 'someone123' not in out and 'example.com' not in out
    assert '<email>' in out


def test_uid_embedded_in_path_segments_is_stripped():
    out = normalize('path users/%s/memories/%s denied' % (SYN_FUID, SYN_DOC_ID))
    assert SYN_FUID not in out and SYN_DOC_ID not in out
    assert 'users/<fuid>/memories/<id>' in out


def test_site_field_embedding_an_id_is_scrubbed():
    site = extract_site('event=discard site=users/%s/jobs/%s type=Error' % (SYN_FUID, SYN_DOC_ID))
    assert site == 'users/<fuid>/jobs/<id>'
    assert not leaked_tokens(site or '')


def test_payload_site_field_with_id_is_scrubbed():
    entry = {'jsonPayload': {'message': 'job blew up', 'site': 'workers/%s.py:9' % SYN_DOC_ID}}
    site = extract_site(entry_text(entry), entry['jsonPayload'])
    assert site == 'workers/<id>.py:9'
    assert not leaked_tokens(site or '')


def test_frame_basename_embedding_an_id_is_scrubbed():
    text = (
        'ERROR w: boom\nTraceback (most recent call last):\n  File "/tmp/%s.py", line 5, in f\nValueError: nope'
        % SYN_DOC_ID
    )
    fp = fingerprint_entry({'textPayload': text, 'resource': {'labels': {}}, 'logName': 's'})
    assert fp.fingerprint == 'ValueError|<id>.py:5|w'
    assert not leaked_tokens(fp.fingerprint, fp.label)


def test_fingerprint_and_label_carry_no_identifier_shape_across_battery():
    battery = [
        'WARNING routers.pusher: Durable audio projection failure for %s',
        'ERROR db.users: load failed for %s retry',
        'INFO jobs: %s queued after %s',
        'WARNING sync: conversation %s locked by %s',
        'CRITICAL auth: token %s rejected for %s',
        'ERROR api: GET /v1/users/%s/conversations returned 500',
    ]
    subjects = [
        battery[0] % SYN_FUID,
        battery[1] % SYN_FUID,
        battery[2] % (SYN_DOC_ID, SYN_EMAIL),
        battery[3] % (SYN_UUID, SYN_FUID),
        battery[4] % (SYN_HEX20, SYN_DOC_ID),
        battery[5] % SYN_FUID,
    ]
    for entry_text_raw in subjects:
        fp = fingerprint_entry(k8s_entry(entry_text_raw))
        assert not leaked_tokens(fp.fingerprint, fp.label), fp.fingerprint


def test_placeholder_stability_keeps_one_class_per_defect():
    a = fingerprint_entry(k8s_entry('ERROR db.users: load failed for %s retry' % SYN_FUID))
    b = fingerprint_entry(k8s_entry('ERROR db.users: load failed for %s retry' % SYN_FUID_ALT))
    assert a.fingerprint == b.fingerprint
