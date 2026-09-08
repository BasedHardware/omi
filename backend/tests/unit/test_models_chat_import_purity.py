"""models/chat.py must not drag the database layer into its import graph.

#11913 added `from database.apps import get_app_by_id_db` at module scope in
`models/chat.py`. Every suite that loads the real chat model then transitively
imported `google.cloud.firestore_v1`, which turned `Backend Unit Tests` red on
main (#11925): 67 tests died on `duplicate file name
google/cloud/firestore_v1/types/document.proto` once the descriptor pool had
already been populated by another module in the same process.

The guard runs the import in a clean interpreter and inspects the real
`sys.modules` it produced, so it fails on any future model-layer import that
reaches persistence — not just this one symbol.
"""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

_PROBE = """
import sys

import models.chat  # noqa: F401

leaked = sorted(
    name
    for name in sys.modules
    if name == 'database' or name.startswith('database.') or name.startswith('google.cloud.firestore')
)
print('\\n'.join(leaked))
"""


def _import_models_chat_in_a_clean_interpreter() -> str:
    result = subprocess.run(
        [sys.executable, '-c', _PROBE],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f'importing models.chat failed:\n{result.stderr}'
    return result.stdout.strip()


def test_importing_models_chat_does_not_import_the_database_layer():
    leaked = _import_models_chat_in_a_clean_interpreter()

    assert leaked == '', (
        'models/chat.py must stay import-pure: importing it pulled in '
        f'{leaked.splitlines()}. Inject a resolver (see Message.get_messages_as_string\'s '
        'app_name_resolver) instead of importing database.* at module scope.'
    )
