"""Immutable backend snapshots shared by replay gates; no checkout or installation."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tarfile
import tempfile


def resolve_refs(repo, ref, base):
    return {
        label: subprocess.check_output(
            ['git', '-C', str(repo), 'rev-parse', '--verify', f'{value}^{{commit}}'],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        for label, value in (('candidate', ref), ('baseline', base))
    }


@contextmanager
def backend_snapshot(repo, sha, output, label):
    with tempfile.TemporaryDirectory(prefix=f'replay-{label}-', dir=output) as directory:
        snapshot = Path(directory)
        archive = snapshot / 'source.tar'
        with archive.open('wb') as stream:
            subprocess.run(
                ['git', '-C', str(repo), 'archive', sha, 'backend'],
                stdout=stream,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        with tarfile.open(archive) as bundle:
            bundle.extractall(snapshot, filter='data')
        archive.unlink()
        yield snapshot / 'backend'
