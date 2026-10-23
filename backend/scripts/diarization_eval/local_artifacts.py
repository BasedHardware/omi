"""Private filesystem adapters for the production worker and projector.

No cloud clients, enrollment acquisition or vendor inference. The assignment
adapter persists projected segments; it does not claim Firestore qualification.
"""

from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from config.policy import ProjectionPolicy
from scripts.diarization_eval.prep_speaker_task import private_dir


def private_json(path, value):
    path = Path(path)
    private_dir(path.parent)
    temporary = path.with_suffix(path.suffix + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump(value, handle, default=str)
    temporary.chmod(0o600)
    temporary.replace(path)


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cache_key(*, audio, crop, source_files, settings):
    evidence = {
        'audio': file_digest(audio),
        'crop': crop,
        'sources': [file_digest(path) for path in source_files],
        'settings': settings,
    }
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


class Artifacts:
    def __init__(self, root):
        self.root = private_dir(root)

    def fetch_audio(self, item):
        return Path(item.audio_uri).read_bytes()

    def persist_result(self, item, payload):
        path = self.root / (item.segment_id + '.json')
        private_json(path, payload)
        return str(path)

    def load_result(self, item, uri):
        return json.loads(Path(uri).read_text())


@dataclass
class LocalSession:
    root: Path
    part_index: int
    policy: ProjectionPolicy

    def prepare(self, transaction, **kwargs):
        return None

    def validate_plan(self, *args, **kwargs):
        return None

    def persist(self, transaction, planned):
        private_json(self.root / f'part-{self.part_index}.json', planned)
        return {'state': 'ready', 'conversation_id': planned['id']}


class LocalProjectionStore:
    client = None

    def __init__(self, root):
        self.root = root

    def session(self, segment_id, binding, now, *, part_index, part_count, policy):
        return LocalSession(self.root, part_index, policy)

    def check(self, session):
        return None


def filesystem_assignment(owner_id, incoming, *, before_assign, validate_plan, after_assign, **kwargs):
    before_assign(None)
    after_assign(None, incoming)
    return incoming, True, incoming['transcript_segments']


def project(artifacts, item, binding, uri, *, policy=None):
    root = artifacts.root / 'projection' / item.segment_id
    store = LocalProjectionStore(root)
    projector_type = importlib.import_module('utils.batch_pipeline.projection').Projector
    projector = projector_type(
        SimpleNamespace(), artifacts.load_result, projection_store=store, assign_conversation=filesystem_assignment
    )
    projector.assign_parts(
        item,
        {'result': {'result_uri': uri}},
        binding,
        policy=policy or ProjectionPolicy(authoritative_labels=True),
        finish=False,
    )
    # Score the persisted output, never the pre-projection diarizer channels.
    turns = []
    for path in sorted(root.glob('part-*.json'), key=lambda p: int(p.stem.split('-')[-1])):
        persisted = json.loads(path.read_text())
        turns.extend(persisted['transcript_segments'])
    return turns
