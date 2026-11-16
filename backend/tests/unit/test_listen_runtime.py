"""Offline runtime admission and extraction/transport boundaries. No downloads."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('listen_runtime', ROOT / '.github/scripts/listen_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
RAW = (ROOT / runtime.MANIFEST).read_bytes()


def tar_file(path, entries):
    with tarfile.open(path, 'w:gz') as archive:
        for name, kind, value in entries:
            row = tarfile.TarInfo(name)
            if kind == 'link':
                row.type, row.linkname = tarfile.SYMTYPE, value
                archive.addfile(row)
            else:
                row.size = len(value)
                archive.addfile(row, io.BytesIO(value))
    return path


def test_manifest_predicts_all_six_runtime_fields_without_local_tool_identity():
    m = runtime.manifest(RAW)
    values = runtime.predicted(RAW)
    assert values == {
        'runtime_manifest_sha256': runtime.sha(RAW),
        'helm_version': 'v3.16.4',
        'helm_sha256': m['helm']['binary_sha256'],
        'python_version': '3.12.9',
        'yaml_version': '6.0.2',
        'yaml_sha256': m['yaml']['module_sha256'],
    }
    assert len(m['yaml']['pure_files_sha256']) == 17
    assert m['python']['setup_action'] is None and m['yaml']['with_libyaml'] is False


@pytest.mark.parametrize('fault', ['field', 'os', 'arch', 'libc', 'native', 'hash', 'extra-yaml', 'limit'])
def test_manifest_unknown_or_changed_platform_policy_refuses(fault):
    m = runtime.manifest(RAW)
    if fault == 'field':
        m['caller_approved'] = True
    elif fault in {'os', 'arch', 'libc'}:
        key = {'os': 'os_version', 'arch': 'architecture', 'libc': 'libc_version'}[fault]
        m['target'][key] = 'unknown'
    elif fault == 'native':
        m['yaml']['with_libyaml'] = True
    elif fault == 'hash':
        m['helm']['binary_sha256'] = 'not-a-digest'
    elif fault == 'extra-yaml':
        m['yaml']['pure_files_sha256']['yaml/evil.py'] = 'a' * 64
    else:
        m['limits']['total_download_bytes'] += 1
    with pytest.raises(runtime.Refused):
        runtime.manifest(json.dumps(m).encode())


@pytest.mark.parametrize(
    'entries',
    [
        [('/absolute', 'file', b'x')],
        [('../escape', 'file', b'x')],
        [('a', 'file', b'x'), ('./a', 'file', b'x')],
        [('a', 'link', '../outside')],
        [('a', 'link', '/outside')],
        [('a', 'link', 'other'), ('a/file', 'file', b'x')],
    ],
)
def test_real_archive_path_link_and_duplicate_headers_refuse(tmp_path, entries):
    p = tar_file(tmp_path / 'bad.tar.gz', entries)
    with pytest.raises(runtime.Refused):
        runtime.inventory(p, 0, 0)
    assert not (tmp_path / 'outside').exists()


def test_archive_and_member_bounds_are_shared_and_never_truncated(tmp_path):
    p = tar_file(tmp_path / 'ok.tar.gz', [('a', 'file', b'valid')])
    for count, size in [(runtime.MEMBERS, 0), (0, runtime.EXPANDED)]:
        with pytest.raises(runtime.Refused, match='runtime_archive_bound'):
            runtime.inventory(p, count, size)
    assert runtime.member_hash(p, 'a') == runtime.sha(b'valid')


@pytest.mark.parametrize('payload', [b'altered', b'expected-and-too-much'])
def test_download_checksum_or_oversize_refuses_before_materialization(tmp_path, payload):
    data = dict(url='https://get.helm.sh/fixed', archive_bytes=8, archive_sha256=runtime.sha(b'expected'))
    with pytest.raises(runtime.Refused):
        runtime.download(data, tmp_path / 'archive', 32, float('inf'), lambda *a, **k: io.BytesIO(payload))
    assert not (tmp_path / 'python').exists()


def test_host_failure_cannot_download_or_execute(tmp_path):
    with patch.object(runtime, 'host', side_effect=runtime.Refused('runtime_host')), patch.object(
        runtime, 'download'
    ) as download, patch.object(runtime, 'run') as execute:
        with pytest.raises(runtime.Refused):
            runtime.stage(RAW, tmp_path / 'stage')
    download.assert_not_called()
    execute.assert_not_called()


@pytest.mark.parametrize(
    'event,paths,expected',
    [
        ('workflow_dispatch', [], {'runtime': False, 'deploy': True}),
        ('pull_request', ['backend/charts/backend-listen/x'], {'runtime': False, 'deploy': False}),
        ('push', ['backend/charts/backend-listen/x'], {'runtime': False, 'deploy': True}),
        ('push', [runtime.MANIFEST], {'runtime': True, 'deploy': False}),
        ('pull_request', [runtime.BOOTSTRAP], {'runtime': True, 'deploy': False}),
        ('push', [runtime.MANIFEST, 'backend/charts/backend-secrets/x'], {'runtime': True, 'deploy': True}),
    ],
)
def test_event_and_exact_path_matrix_preserves_normal_chart_deploy(event, paths, expected):
    assert runtime.classify(event, paths) == expected


@pytest.mark.parametrize('paths', [[], ['../escape'], ['/x'], ['a\nb'], ['x'] * 2001])
def test_ambiguous_or_beyond_bound_classification_never_grants_writers(paths):
    with pytest.raises(runtime.Refused):
        runtime.classify('push', paths)


def test_actual_child_output_bound_and_timeout_reap_children_without_stderr():
    for code, timeout in [('print("x"*20000)', 2), ('import time;time.sleep(20)', 0.05)]:
        children, real = [], subprocess.Popen

        def start(*args, **kwargs):
            child = real(*args, **kwargs)
            children.append(child)
            return child

        with patch.object(runtime.subprocess, 'Popen', side_effect=start):
            with pytest.raises(runtime.Refused):
                runtime.run([sys.executable, '-c', code], dict(runtime.os.environ), timeout=timeout)
        assert len(children) == 1 and children[0].returncode is not None


def test_runtime_manifest_and_bootstrap_failure_output_is_fixed_not_payload(tmp_path):
    source = tmp_path / 'private.json'
    source.write_text('{"secret":"NEVER_PRINT_RUNTIME_CANARY"}')
    result = subprocess.run(
        [sys.executable, str(ROOT / runtime.BOOTSTRAP), 'measure', '--manifest', str(source), '--root', str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stderr == 'LISTEN_RUNTIME_UNKNOWN\n' and result.stdout == ''


@pytest.mark.parametrize('fault', ['python_version', 'yaml_sha256', 'runtime_manifest_sha256', 'helm_version'])
def test_measurement_compares_actual_probe_identity_not_just_a_version_regex(tmp_path, fault):
    # Offline transport model only, never a claim that M1 ran Linux ELF.
    m = runtime.manifest(RAW)
    for file, data in [('python/bin/python3.12', b'python'), ('helm/linux-amd64/helm', b'helm')]:
        p = tmp_path / file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    measured = runtime.predicted(RAW)
    if fault != 'helm_version':
        measured[fault] = '3.12.10' if fault == 'python_version' else '0' * 64
    measured.pop('helm_version')
    original_digest = runtime.sha

    def digest(data):
        if data == RAW:
            return original_digest(data)
        return m['python']['binary_sha256'] if data == b'python' else m['helm']['binary_sha256']

    def execute(argv, env):
        if argv[0].endswith('/helm'):
            return b'v3.16.5' if fault == 'helm_version' else b'v3.16.4'
        return json.dumps(measured).encode()

    with patch.object(runtime, 'host'), patch.object(runtime, 'sha', side_effect=digest), patch.object(
        runtime, 'run', side_effect=execute
    ):
        with pytest.raises(runtime.Refused, match='runtime_identity_mismatch'):
            runtime.measured(RAW, tmp_path)
