"""Load the actual pre-PR worker without replacing the current process's modules.

Both changed worker modules are frozen byte-for-byte, including the local import
in run_job. All their other first-party dependencies are unchanged by this PR.
Snapshots make the proof independent of Git history in shallow CI checkouts.
"""

import builtins
import hashlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

BASE = 'f47914db8856fdb9f0be165b489e066f04088192'
DIGESTS = {
    'conversation_batch_purge_jobs': '6e4e3979ecb4cef401539929e31228d878ff613df1cc7fe1ea4c84776c87a8b5',
    'batch_pipeline_conversation_purge': '9028120e899f4a1f0ebc67a863c185041ac02da12ecd57ee93dfde0e9b5f25f5',
}


def load_worker():
    modules = {}

    def worker_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'database.batch_pipeline_conversation_purge':
            return modules['batch_pipeline_conversation_purge']
        return builtins.__import__(name, globals, locals, fromlist, level)

    root = Path(__file__).parents[1] / 'fixtures' / 'purge_pre_coalescing'
    for name, digest in DIGESTS.items():
        path = root / f'{name}.py.txt'
        source = path.read_bytes()
        assert hashlib.sha256(source).hexdigest() == digest, f'pre-PR fixture changed: {path}'
        module = ModuleType(f'pre_coalescing_{name}')
        module.__dict__['__builtins__'] = {**vars(builtins), '__import__': worker_import}
        exec(compile(source, str(path), 'exec'), module.__dict__)
        modules[name] = module
    return SimpleNamespace(
        jobs=modules['conversation_batch_purge_jobs'], purge=modules['batch_pipeline_conversation_purge']
    )
