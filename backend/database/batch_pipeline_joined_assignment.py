"""Transaction-local assignment writes for a joined publication."""

from collections import defaultdict
from copy import deepcopy

from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_store import FirestoreTransaction


class JoinedAssignmentWrites:
    def __init__(self, transaction):
        self.read_transaction = transaction
        self.operations = []
        self.by_path = defaultdict(list)
        self.originals = {}

    def set(self, ref, value):
        self._stage('set', ref, value)

    def update(self, ref, value):
        self._stage('update', ref, value)

    def _stage(self, operation, ref, value):
        self.operations.append((operation, ref, value))
        self.by_path[ref.path].append((operation, value))

    def discard_since(self, checkpoint):
        for _, ref, _ in reversed(self.operations[checkpoint:]):
            self.by_path[ref.path].pop()
        del self.operations[checkpoint:]

    def read_assignment_document(self, ref):
        if ref.path not in self.originals:
            self.originals[ref.path] = ref.get(transaction=self.read_transaction).to_dict()
        row = deepcopy(self.originals[ref.path])
        for operation, value in self.by_path.get(ref.path, ()):
            if operation == 'set':
                row = deepcopy(value)
                continue
            if row is None:
                raise ProjectionBlocked('joined assignment update has no base document')
            for key, field in value.items():
                *parents, leaf = FieldPath.from_string(key).parts
                target = row
                for parent in parents:
                    target = target.setdefault(parent, {})
                if field is firestore.DELETE_FIELD:
                    target.pop(leaf, None)
                elif isinstance(field, firestore.ArrayUnion):
                    values = target.get(leaf)
                    merged = list(values) if isinstance(values, list) else []
                    for member in deepcopy(field.values):
                        if member not in merged:
                            merged.append(member)
                    target[leaf] = merged
                else:
                    target[leaf] = deepcopy(field)
        return row

    def flush(self, client, namespace):
        for operation, ref, value in self.operations:
            getattr(self.read_transaction, operation)(ref, value)
        FirestoreTransaction(client, namespace, self.read_transaction).check_joined_commit_budget()
