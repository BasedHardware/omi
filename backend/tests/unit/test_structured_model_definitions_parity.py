"""The structured model the prod image loads must behave like the one the unit tests load.

``models/structured.py`` imports ``omi_plugin_sdk.models`` when the checkout has the plugin SDK, and
otherwise defines its own fallback copy. Runtime images copy only ``backend/``, so production runs the
fallback while every other unit test validates against the SDK copy. On 2026-11-17 a participant-source
repair had to be written twice (#25588). This test fails when the two definitions drift: same JSON
schema, same validators and serializers, and the same validated output (or the same rejection) for a
corpus of stored-row shapes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from models import structured

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODELS = ('ActionItem', 'Event', 'Insight', 'NoteClaim', 'NoteEvidenceRef', 'Participant', 'Section', 'Structured')

# Shapes stored rows actually carry, including legacy and malformed ones the readers must repair or reject.
CORPUS = [
    {},
    {'title': 'Plan', 'overview': 'o', 'emoji': '🛠', 'category': 'work'},
    {'title': 't', 'category': 'not-a-category'},
    {'title': 't', 'category': None},
    {'participants': [{'name': 'Alex'}, {'name': 'Sam', 'source': 'roster'}, {'name': 'Kim', 'source': 'screen'}]},
    {'participants': [{'name': 'Lee', 'source': 'background', 'is_ai_agent': True, 'email': 'e'}]},
    {'participants': [{'name': 'A', 'source': 'transcript', 'speaker_bindings': [1, 1, -2, 'x', 3]}]},
    {'participants': [{'name': 'A', 'source': 'unknown'}]},
    {'participants': 'not-a-list'},
    {'sections': [{'heading': 'H', 'body_markdown': 'B'}, {'heading': 'S', 'body_markdown': '', 'kind': 'side_notes'}]},
    {'sections': [{'heading': 'H'}]},
    {
        'action_items': [{'description': 'Call Sam', 'completed': True, 'due_at': '2026-11-17T10:00:00Z'}],
        'events': [{'title': 'Sync', 'start': '2026-11-18T09:00:00Z', 'duration': 30, 'description': 'd'}],
    },
    {'action_items': [{'completed': False}]},
    {'meeting_type': 'planning', 'salience': 'highlight', 'gist': 'g', 'title_provenance': 'server_minimum'},
    {'meeting_type': 'brunch'},
    {'insights': [{'text': 'i', 'kind': 'goal'}]},
    {
        'note_claims': [
            {
                'target': '/overview',
                'text': 'c',
                'evidence_ids': ['e1'],
                'provenance': 'said',
                'evidence_sources': [{'id': 'e1', 'source_kind': 'transcript'}],
            }
        ]
    },
]

PROBE = r'''
import json, sys

def describe(module, models, corpus):
    out = {'module': module.Structured.__module__, 'schemas': {}, 'decorators': {}, 'corpus': []}
    for name in models:
        cls = getattr(module, name)
        out['schemas'][name] = cls.model_json_schema()
        decorators = cls.__pydantic_decorators__
        out['decorators'][name] = {
            kind: sorted(getattr(decorators, kind))
            for kind in ('validators', 'field_validators', 'root_validators', 'field_serializers',
                         'model_serializers', 'model_validators', 'computed_fields')
        }
    for payload in corpus:
        try:
            value = module.Structured.model_validate(payload)
        except Exception as error:
            errors = getattr(error, 'errors', None)
            detail = [
                ['.'.join(str(p) for p in item['loc']), item['type']]
                for item in errors(include_input=False, include_url=False)
            ] if errors else type(error).__name__
            out['corpus'].append({'error': detail})
            continue
        out['corpus'].append({'dump': value.model_dump(mode='json'), 'str': str(value)})
    return out
'''

FALLBACK = r'''
import builtins, json, sys

real_import = builtins.__import__

def block_optional_sdk(name, *args, **kwargs):
    if name == "omi_plugin_sdk" or name.startswith("omi_plugin_sdk."):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = block_optional_sdk
from models import structured
models, corpus = json.loads(sys.stdin.read())
print(json.dumps(describe(structured, models, corpus), sort_keys=True, default=str))
'''


def _describe_in_process():
    namespace: dict = {}
    exec(PROBE, namespace)  # noqa: S102 -- the same describe() runs on both sides
    return json.loads(json.dumps(namespace['describe'](structured, MODELS, CORPUS), sort_keys=True, default=str))


def _describe_fallback(tmp_path):
    # The runtime image's view: backend/models without the plugin SDK beside it.
    models_root = tmp_path / 'models'
    models_root.mkdir()
    for name in ('__init__.py', 'conversation_enums.py', 'structured.py', 'task_due.py'):
        shutil.copy(BACKEND_DIR / 'models' / name, models_root / name)
    environment = {**os.environ, 'PYTHONPATH': str(tmp_path)}
    result = subprocess.run(
        [sys.executable, '-c', PROBE + FALLBACK],
        input=json.dumps([MODELS, CORPUS]),
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f'fallback probe failed: {result.stderr[-2000:]}'
    return json.loads(result.stdout)


def test_tests_load_the_sdk_copy_so_the_comparison_is_between_two_definitions():
    assert structured.Structured.__module__ == 'omi_plugin_sdk.models'


def test_fallback_structured_model_matches_the_sdk_copy(tmp_path):
    sdk, fallback = _describe_in_process(), _describe_fallback(tmp_path)
    assert fallback['module'] == 'models.structured'
    for name in MODELS:
        assert fallback['schemas'][name] == sdk['schemas'][name], f'{name} JSON schema drifted'
        assert fallback['decorators'][name] == sdk['decorators'][name], f'{name} validators/serializers drifted'
    for payload, expected, actual in zip(CORPUS, sdk['corpus'], fallback['corpus']):
        assert actual == expected, f'validated output drifted for {payload!r}'
