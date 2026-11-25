"""Closed, bounded listen-evidence runtime. No credentials or production IO."""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request

MANIFEST = '.github/scripts/listen_runtime_manifest.json'
BOOTSTRAP = '.github/scripts/listen_runtime.py'
HASH = re.compile('[0-9a-f]{64}')
SHA = re.compile('[0-9a-f]{40}')
CAP = 160 * 1024 * 1024
EXPANDED = 512 * 1024 * 1024
MEMBERS = 12000
SECONDS = 240


class Refused(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'runtime_duplicate_key')
        result[key] = value
    return result


def manifest(raw):
    require(len(raw) <= 16384, 'runtime_manifest_size')
    m = json.loads(raw, object_pairs_hook=unique)
    require(
        set(m) == {'schema', 'purpose', 'target', 'helm', 'python', 'yaml', 'actions', 'limits'}
        and m['schema'] == 1
        and m['purpose'] == 'listen-overlay-evidence-runtime',
        'runtime_manifest_schema',
    )
    require(
        m['target']
        == {
            'runner_label': 'ubuntu-22.04',
            'os_id': 'ubuntu',
            'os_version': '22.04',
            'kernel': 'Linux',
            'architecture': 'x86_64',
            'elf_class': 'ELF64',
            'libc_family': 'glibc',
            'libc_version': '2.35',
            'container': None,
            'python_compiled_prefix': '/opt/hostedtoolcache/Python/3.12.9/x64',
            'python_stage': 'RUNNER_TEMP/listen-runtime/python',
        },
        'runtime_target',
    )
    require(
        set(m['helm'])
        == {
            'version',
            'url',
            'archive_bytes',
            'archive_sha256',
            'binary_member',
            'binary_bytes',
            'binary_sha256',
            'checksum_url',
        },
        'runtime_helm_schema',
    )
    require(
        set(m['python'])
        == {
            'version',
            'source_repository',
            'source_commit',
            'release_tag',
            'url',
            'archive_bytes',
            'archive_sha256',
            'checksums_url',
            'checksums_sha256',
            'binary_member',
            'binary_sha256',
            'libpython_member',
            'libpython_sha256',
            'setup_action',
            'setup_method',
            'runtime_loader',
        },
        'runtime_python_schema',
    )
    require(
        set(m['yaml'])
        == {
            'version',
            'filename',
            'url',
            'archive_bytes',
            'archive_sha256',
            'method',
            'module_member',
            'module_sha256',
            'pure_files_sha256',
            'with_libyaml',
        },
        'runtime_yaml_schema',
    )
    require(m['python']['setup_action'] is None and m['yaml']['with_libyaml'] is False, 'runtime_native_dependency')
    require(
        m['helm']['binary_member'] == 'linux-amd64/helm'
        and m['python']['binary_member'] == './bin/python3.12'
        and m['python']['libpython_member'] == './lib/libpython3.12.so.1.0'
        and m['yaml']['module_member'] == 'pyyaml-6.0.2/lib/yaml/__init__.py',
        'runtime_member',
    )
    for tool, prefix, limit in [
        ('helm', 'https://get.helm.sh/', 32 * 1024**2),
        ('python', 'https://github.com/actions/python-versions/releases/download/', 128 * 1024**2),
        ('yaml', 'https://files.pythonhosted.org/packages/', 1024**2),
    ]:
        data = m[tool]
        require(
            isinstance(data['url'], str)
            and data['url'].startswith(prefix)
            and not any(c in data['url'] for c in '\r\n?#')
            and type(data['archive_bytes']) is int
            and 0 < data['archive_bytes'] <= limit,
            'runtime_artifact',
        )
        require(re.fullmatch('v?[0-9]+\\.[0-9]+\\.[0-9]+', data['version']), 'runtime_version')
        for key, value in data.items():
            if key.endswith('_sha256') and key != 'pure_files_sha256':
                require(isinstance(value, str) and HASH.fullmatch(value), 'runtime_hash')
    files = m['yaml']['pure_files_sha256']
    require(
        isinstance(files, dict)
        and len(files) == 17
        and files.get('yaml/__init__.py') == m['yaml']['module_sha256']
        and all(re.fullmatch('yaml/[a-z_]+\\.py', k) and HASH.fullmatch(v) for k, v in files.items()),
        'runtime_yaml_inventory',
    )
    require(
        set(m['actions']) == {'checkout', 'auth', 'setup-gcloud', 'get-gke-credentials', 'upload-artifact'}
        and all(isinstance(v, str) and SHA.fullmatch(v) for v in m['actions'].values()),
        'runtime_actions',
    )
    require(
        m['limits']
        == {
            'artifact_download_calls': 3,
            'total_download_bytes': CAP,
            'helm_archive_bytes': 32 * 1024**2,
            'python_archive_bytes': 128 * 1024**2,
            'yaml_archive_bytes': 1024**2,
            'expanded_bytes': EXPANDED,
            'tar_members': MEMBERS,
            'runtime_bootstrap_seconds': SECONDS,
            'per_download_seconds': 60,
            'reconstruction_ci_minutes': 5,
        },
        'runtime_limits',
    )
    return m


def predicted(raw):
    m = manifest(raw)
    return {
        'runtime_manifest_sha256': sha(raw),
        'helm_version': m['helm']['version'],
        'helm_sha256': m['helm']['binary_sha256'],
        'python_version': m['python']['version'],
        'yaml_version': m['yaml']['version'],
        'yaml_sha256': m['yaml']['module_sha256'],
    }


def host(m):
    os_release = platform.freedesktop_os_release()
    require(
        platform.system() == 'Linux'
        and platform.machine() == 'x86_64'
        and os_release.get('ID') == 'ubuntu'
        and os_release.get('VERSION_ID') == '22.04'
        and os.confstr('CS_GNU_LIBC_VERSION') == 'glibc 2.35',
        'runtime_host',
    )


def download(data, path, remaining, deadline, opener=urllib.request.urlopen):
    require(time.monotonic() < deadline, 'runtime_deadline')
    expected = data['archive_bytes']
    require(expected <= remaining, 'runtime_download_bound')
    start, count = time.monotonic(), 0
    with opener(data['url'], timeout=min(60, max(1, deadline - start))) as response, path.open('xb') as output:
        while True:
            require(time.monotonic() < min(deadline, start + 60), 'runtime_download_deadline')
            chunk = response.read(min(1024 * 1024, expected - count + 1))
            if not chunk:
                break
            count += len(chunk)
            require(count <= expected and count <= remaining, 'runtime_download_bound')
            output.write(chunk)
    require(count == expected and sha(path.read_bytes()) == data['archive_sha256'], 'runtime_archive_checksum')
    return count


def inventory(path, count, expanded):
    """Validate headers before any extraction. Exact archive hash closes the inventory."""
    seen, rows = set(), []
    with tarfile.open(path, 'r:gz') as archive:
        for item in archive:
            count += 1
            expanded += item.size
            require(item.size >= 0 and count <= MEMBERS and expanded <= EXPANDED, 'runtime_archive_bound')
            parts = PurePosixPath(item.name).parts
            normalized = str(PurePosixPath(item.name))
            require(
                not item.name.startswith('/')
                and '..' not in parts
                and normalized not in seen
                and not any(c in item.name for c in '\0\n\r')
                and len(item.name) <= 512,
                'runtime_archive_path',
            )
            seen.add(normalized)
            require(item.isdir() or item.isfile() or item.issym(), 'runtime_archive_type')
            if item.issym():
                target = PurePosixPath(item.linkname)
                require(
                    not target.is_absolute() and '..' not in target.parts and '\0' not in item.linkname,
                    'runtime_archive_link',
                )
            rows.append(item)
        # No file may be materialized through an archive-provided symlink.
        links = {PurePosixPath(x.name) for x in rows if x.issym()}
        require(all(not any(p in links for p in PurePosixPath(x.name).parents) for x in rows), 'runtime_link_parent')
    return rows, count, expanded


def member_hash(path, name):
    with tarfile.open(path, 'r:gz') as archive:
        item = archive.getmember(name)
        require(item.isfile() and item.size <= 64 * 1024**2, 'runtime_member')
        return sha(archive.extractfile(item).read())


def materialize(archive_path, rows, target, *, yaml_files=None):
    target.mkdir(mode=0o700)
    with tarfile.open(archive_path, 'r:gz') as archive:
        for item in rows:
            name = item.name
            if yaml_files is not None:
                if '/lib/' not in name or name.split('/lib/', 1)[1] not in yaml_files:
                    continue
                name = name.split('/lib/', 1)[1]
                require(item.isfile(), 'runtime_yaml_file')
            out = target / name
            if item.isdir():
                out.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif item.isfile():
                out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with out.open('xb') as stream:
                    shutil.copyfileobj(archive.extractfile(item), stream)
                out.chmod(0o700 if item.mode & 0o111 else 0o600)
        # Only validated relative links, after all regular files exist.
        if yaml_files is None:
            for item in rows:
                if item.issym():
                    out = target / item.name
                    require(
                        (out.parent / item.linkname).resolve().is_relative_to(target.resolve()), 'runtime_link_escape'
                    )
                    out.symlink_to(item.linkname)


def stage(raw, root, opener=urllib.request.urlopen):
    m = manifest(raw)
    host(m)  # No download on the wrong host.
    root.mkdir(mode=0o700, parents=False)
    deadline, count, expanded, downloaded = time.monotonic() + SECONDS, 0, 0, 0
    archives, inventories = {}, {}
    try:
        for name in ('helm', 'python', 'yaml'):
            path = root / (name + '.tar.gz')
            downloaded += download(m[name], path, CAP - downloaded, deadline, opener)
            archives[name] = path
        for name in archives:
            rows, count, expanded = inventory(archives[name], count, expanded)
            inventories[name] = rows
        for name, member, expected in [
            ('helm', m['helm']['binary_member'], m['helm']['binary_sha256']),
            ('python', m['python']['binary_member'], m['python']['binary_sha256']),
            ('python', m['python']['libpython_member'], m['python']['libpython_sha256']),
            ('yaml', m['yaml']['module_member'], m['yaml']['module_sha256']),
        ]:
            require(member_hash(archives[name], member) == expected, 'runtime_member_checksum')
        with tarfile.open(archives['yaml'], 'r:gz') as archive:
            actual = {
                x.name.split('/lib/', 1)[1]: sha(archive.extractfile(x).read())
                for x in inventories['yaml']
                if x.isfile() and '/lib/yaml/' in x.name
            }
        require(actual == m['yaml']['pure_files_sha256'], 'runtime_yaml_inventory')
        require(time.monotonic() < deadline, 'runtime_deadline')
        materialize(archives['python'], inventories['python'], root / 'python')
        materialize(archives['helm'], inventories['helm'], root / 'helm')
        site = root / 'python/lib/python3.12/site-packages'
        require(not (site / 'yaml').exists(), 'runtime_preinstalled_yaml')
        # Isolate YAML from any bundled Python packaging dependencies.
        materialize(archives['yaml'], inventories['yaml'], root / 'parser', yaml_files=m['yaml']['pure_files_sha256'])
        shutil.copytree(root / 'parser/yaml', site / 'yaml')
        require(time.monotonic() < deadline, 'runtime_deadline')
        return m
    except BaseException:
        shutil.rmtree(root)
        raise


def run(argv, env, *, timeout=20):
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    primary = None
    deadline = time.monotonic() + timeout
    try:
        out = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() < deadline, 'runtime_process_timeout')
                for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 16385 - len(out))
                    out.extend(chunk)
                    require(len(out) <= 16384, 'runtime_process_bound')
                    if not chunk:
                        selector.unregister(key.fileobj)
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        require(child.returncode == 0, 'runtime_process_failed')
        return bytes(out)
    except BaseException as error:
        primary = error
        raise
    finally:
        # Descendants can keep stdout open after the direct child exits. The
        # private process group remains owned by this invocation until collected.
        cleanup = []
        try:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as error:
                # Only a terminal direct child makes EPERM ignorable. A live
                # denial cannot prove descendant cleanup, even if kill works.
                terminal = False
                try:
                    terminal = child.poll() is not None
                except OSError:
                    cleanup.append('runtime_process_poll_failed')
                if not isinstance(error, PermissionError) or not terminal:
                    cleanup.append('runtime_process_cleanup_denied')
                    try:
                        child.kill()
                    except OSError:
                        cleanup.append('runtime_process_child_kill_denied')
            try:
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except (subprocess.TimeoutExpired, OSError):
                cleanup.append('runtime_process_reap_failed')
        finally:
            try:
                child.stdout.close()
            except OSError:
                cleanup.append('runtime_process_close_failed')
        if cleanup:
            if primary is not None:
                # Fixed codes only: preserve the original refusal without
                # exposing private command output or OS exception payloads.
                primary.add_note(','.join(cleanup))
            else:
                raise Refused(','.join(cleanup)) from None


def environment(root):
    env = {
        k: v for k, v in os.environ.items() if k not in {'PYTHONHOME', 'PYTHONPATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH'}
    }
    env['LD_LIBRARY_PATH'] = str(root / 'python/lib')
    env['PATH'] = str(root / 'helm/linux-amd64') + ':' + str(root / 'python/bin') + ':' + env.get('PATH', '')
    return env


def measured(raw, root):
    m = manifest(raw)
    host(m)
    root = root.resolve()
    python = root / 'python/bin/python3.12'
    helm = root / 'helm/linux-amd64/helm'
    require(
        sha(python.read_bytes()) == m['python']['binary_sha256']
        and sha(helm.read_bytes()) == m['helm']['binary_sha256'],
        'runtime_binary_changed',
    )
    env = environment(root)
    # Same checked-out helper, executed by VERIFIED staged Python rather than the bootstrap interpreter.
    observed = json.loads(
        run([str(python), '-I', '-B', str(Path(__file__).resolve()), '_probe', '--root', str(root)], env)
    )
    observed['helm_version'] = run([str(helm), 'version', '--template', '{{.Version}}'], env).decode().strip()
    require(observed == predicted(raw), 'runtime_identity_mismatch')
    return observed


def running(raw, root):
    """Validate the producer's actual interpreter/imports without trusting a saved JSON report."""
    m = manifest(raw)
    host(m)
    root = root.resolve()
    parser = importlib.import_module('yaml')
    require(
        Path(sys.prefix).resolve() == root / 'python'
        and Path(sys.base_prefix).resolve() == root / 'python'
        and Path(sys.executable).resolve() == root / 'python/bin/python3.12',
        'runtime_python_prefix',
    )
    require(
        Path(parser.__file__).resolve() == root / 'python/lib/python3.12/site-packages/yaml/__init__.py'
        and parser.__with_libyaml__ is False,
        'runtime_yaml_import',
    )
    libs = {line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if 'libpython3.12.so' in line}
    require(
        libs == {str(root / 'python/lib/libpython3.12.so.1.0')}
        and sha(Path(next(iter(libs))).read_bytes()) == m['python']['libpython_sha256'],
        'runtime_loaded_library',
    )
    files = {'yaml/' + p.name: sha(p.read_bytes()) for p in Path(parser.__file__).parent.iterdir() if p.is_file()}
    require(files == m['yaml']['pure_files_sha256'], 'runtime_import_inventory')
    require(sha(Path(sys.executable).read_bytes()) == m['python']['binary_sha256'], 'runtime_python_changed')
    result = {
        'python_version': platform.python_version(),
        'yaml_version': parser.__version__,
        'yaml_sha256': sha(Path(parser.__file__).read_bytes()),
        'runtime_manifest_sha256': sha(raw),
        'helm_sha256': sha((root / 'helm/linux-amd64/helm').read_bytes()),
    }
    require(result == {k: v for k, v in predicted(raw).items() if k != 'helm_version'}, 'runtime_identity_mismatch')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['reconstruct', 'measure', '_probe'])
    p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('listen_runtime_manifest.json'))
    p.add_argument('--root', type=Path)
    a = p.parse_args()

    def interrupted(_sig, _frame):
        raise Refused('runtime_interrupted')

    for sig in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    signal.alarm(SECONDS)
    try:
        raw = a.manifest.read_bytes()
        require(a.root is not None and a.root.is_absolute(), 'runtime_root')
        if a.mode == 'reconstruct':
            stage(raw, a.root)
        print(json.dumps(running(raw, a.root) if a.mode == '_probe' else measured(raw, a.root), sort_keys=True))
    except (Exception, KeyboardInterrupt):
        print('LISTEN_RUNTIME_UNKNOWN', file=__import__('sys').stderr)
        return 2
    finally:
        signal.alarm(0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
