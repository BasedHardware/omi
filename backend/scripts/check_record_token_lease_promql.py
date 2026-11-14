#!/usr/bin/env python3
"""Run the real PromQL proof with a checksum-pinned, locally cached promtool."""

import hashlib
import os
from pathlib import Path
import platform
import runpy
import sys
import tarfile
import tempfile
import urllib.request

VERSION = '2.55.1'
ARCHIVES = {
    ('Darwin', 'x86_64'): ('darwin-amd64', 'ba915f45b680566646fc824f2b9793dbcd2741c157a5a599be2cb4665b38b498'),
    ('Linux', 'aarch64'): ('linux-arm64', 'af43368bc6379c3c8bd5ac0b82208060bba22267bf01ad3ab5df56ad5725bf88'),
    ('Linux', 'x86_64'): ('linux-amd64', '19700bdd42ec31ee162e4079ebda4cd0a44432df4daa637141bdbea4b1cd8927'),
    ('Darwin', 'arm64'): ('darwin-arm64', '551d557d8b4e5e5ed4fdbfea9622034f6e9ee760986d876736ced885b764bae9'),
}


def promtool():
    supplied = os.environ.get('PROMTOOL')
    if supplied:
        return Path(supplied).resolve(strict=True)
    target, digest = ARCHIVES[platform.system(), platform.machine()]
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'omi-promtool' / VERSION / target
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / 'prometheus.tar.gz'
    # Verify every cached archive before extracting the one required binary.
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        url = f'https://github.com/prometheus/prometheus/releases/download/v{VERSION}/prometheus-{VERSION}.{target}.tar.gz'
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as temporary:
            path = Path(temporary.name)
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    while chunk := response.read(1024 * 1024):
                        temporary.write(chunk)
                temporary.flush()
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError('promtool archive checksum mismatch')
                path.replace(archive)
            finally:
                path.unlink(missing_ok=True)
    with tarfile.open(archive) as bundle:
        member = bundle.extractfile(f'prometheus-{VERSION}.{target}/promtool')
        if member is None:
            raise ValueError('promtool is missing from verified archive')
        binary = cache / 'promtool'
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as executable:
            path = Path(executable.name)
            try:
                executable.write(member.read())
                executable.flush()
                path.chmod(0o755)
                path.replace(binary)
            finally:
                path.unlink(missing_ok=True)
    return binary


def main():
    backend = Path(__file__).resolve().parents[1]
    binary = promtool()
    for filename in ('tests/promql/record_token_lease.py', 'tests/promql/firestore_cost_budget.py'):
        script = backend / filename
        sys.argv = [str(script), '--promtool', str(binary)]
        runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
