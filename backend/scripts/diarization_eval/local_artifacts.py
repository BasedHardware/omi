"""Private filesystem adapters for the production worker and projector.

No cloud clients, enrollment acquisition or vendor inference. The assignment
adapter persists projected segments; it does not claim Firestore qualification.
"""

import argparse
from dataclasses import asdict, dataclass
from functools import partial
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import subprocess
from types import SimpleNamespace

from config.policy import ProjectionPolicy
from scripts.diarization_eval.prep_speaker_task import private_dir
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem


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


def filesystem_assignment(owner_id, incoming, *, before_assign, validate_plan, after_assign, allocator=None, **kwargs):
    from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

    before_assign(None)
    allocator = allocator or ConversationSpeakerIdAllocator()
    for segment in incoming['transcript_segments']:
        allocator.assign(segment)
    validate_plan(None, incoming)
    after_assign(None, incoming)
    return incoming, True, incoming['transcript_segments']


def project(artifacts, item, binding, uri, *, policy=None):
    from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

    root = artifacts.root / 'projection' / item.segment_id
    store = LocalProjectionStore(root)
    projector_type = importlib.import_module('utils.batch_pipeline.projection').Projector
    projector = projector_type(
        SimpleNamespace(),
        artifacts.load_result,
        projection_store=store,
        assign_conversation=partial(filesystem_assignment, allocator=ConversationSpeakerIdAllocator()),
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


def project_external(python, artifacts, item, binding, uri):
    """Keep the model runtime separate from the pinned backend projection env."""
    request = artifacts.root / 'projection-request.json'
    response = artifacts.root / 'projection-response.json'
    encoded = asdict(item)
    encoded['priority'] = item.priority.value
    private_json(request, {'root': str(artifacts.root), 'item': encoded, 'binding': asdict(binding), 'uri': uri})
    completed = subprocess.run(
        [str(python), str(Path(__file__).resolve()), '--request', str(request), '--response', str(response)],
        capture_output=True,
    )
    if completed.returncode:
        # The caller captures this within its private model log.
        private_json(artifacts.root / 'projection-failure.json', {'stderr': completed.stderr.decode(errors='replace')})
        raise RuntimeError('local_projection_failed')
    return json.loads(response.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--response', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    os.environ['ENCRYPTION_SECRET'] = secrets.token_hex(32)
    request = json.loads(args.request.read_text())
    request['binding']['segment_ids'] = tuple(request['binding']['segment_ids'])
    turns = project(
        Artifacts(request['root']), WorkItem(**request['item']), ProjectionBinding(**request['binding']), request['uri']
    )
    private_json(args.response, turns)


if __name__ == '__main__':
    main()
