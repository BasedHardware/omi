"""Conversation fence walk: budget per distinct document, checks per source."""

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed


class Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class Document:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def get(self, transaction=None):
        self.store.reads.append(self.path)
        return Snapshot(self.store.rows.get(self.path))

    def collection(self, name):
        return Collection(self.store, f'{self.path}/{name}')


class Collection:
    def __init__(self, store, path):
        self.store, self.path = store, path

    def document(self, doc_id):
        return Document(self.store, f'{self.path}/{doc_id}')


class Client:
    def __init__(self, conversations, deleted=()):
        self.reads = []
        self.rows = {'users/owner': {'data_protection_level': 'standard'}}
        for doc_id, row in conversations.items():
            self.rows[f'users/owner/conversations/{doc_id}'] = row
        for doc_id in deleted:
            self.rows[f'users/owner/deleted_conversations/{doc_id}'] = {}

    def collection(self, name):
        return Collection(self, name)

    def conversation_reads(self):
        return [path for path in self.reads if '/conversations/' in path and 'deleted_' not in path]


def merge_cascade(donors=42, max_hops=17):
    """A sync merge cascade: each donor redirects through earlier donors to one target."""
    rows = {'target': {}}
    for n in range(donors):
        parent = f'donor-{n - 1}' if n % max_hops else 'target'
        rows[f'donor-{n}'] = {'deleted': True, 'sync_merged_into': parent}
    return rows, list(rows)


def per_step_cost(rows, sources):
    """What the per-source walk charged before distinct-document accounting."""
    total = 0
    for source in sources:
        current = source
        while True:
            total += 1
            current = rows[current].get('sync_merged_into')
            if current is None:
                break
    return total


def fence(client, sources):
    return assert_batch_write_allowed(client, None, 'owner', conversation_ids=sources)


def test_converging_merge_cascade_charges_each_distinct_document_once():
    rows, sources = merge_cascade()
    assert max(per_step_cost(rows, [source]) for source in sources) - 1 == 17  # redirect hops
    assert per_step_cost(rows, sources) > 256  # The per-step walk exhausted the budget.
    client = Client(rows)
    assert fence(client, sources) == 0
    reads = client.conversation_reads()
    assert len(reads) == len(set(reads)) == len(rows) < 256


def test_shared_redirect_tail_is_read_once_across_sources():
    rows = {f'hop-{n}': {'deleted': True, 'sync_merged_into': f'hop-{n + 1}'} for n in range(10)}
    rows['hop-10'] = {}
    rows.update({f'donor-{n}': {'deleted': True, 'sync_merged_into': 'hop-0'} for n in range(45)})
    client = Client(rows)
    fence(client, [f'donor-{n}' for n in range(45)])
    assert len(client.conversation_reads()) == len(rows)


@pytest.mark.parametrize('position', ['source', 'mid-chain', 'shared-tail', 'target'])
def test_tombstone_anywhere_still_blocks(position):
    rows, sources = merge_cascade()
    tombstoned = {
        'source': sources[-1],
        'mid-chain': 'donor-24',
        'shared-tail': 'donor-17',
        'target': 'target',
    }[position]
    with pytest.raises(BatchPrivacyBlocked) as blocked:
        fence(Client(rows, deleted=[tombstoned]), sources)
    assert blocked.value.reason.value == 'conversation_deleted'


def test_deleted_donor_without_redirect_still_blocks():
    rows, sources = merge_cascade()
    rows['donor-30'] = {'deleted': True}
    with pytest.raises(BatchPrivacyBlocked) as blocked:
        fence(Client(rows), sources)
    assert blocked.value.reason.value == 'conversation_deleted'


@pytest.mark.parametrize('extra', [False, True])
def test_redirect_cycle_still_blocks(extra):
    rows = {
        'a': {'deleted': True, 'sync_merged_into': 'b'},
        'b': {'deleted': True, 'sync_merged_into': 'c'},
        'c': {'deleted': True, 'sync_merged_into': 'a'},
        'live': {},
    }
    sources = ['live', 'a', 'b'] if extra else ['a']
    with pytest.raises(BatchPrivacyBlocked) as blocked:
        fence(Client(rows), sources)
    assert blocked.value.reason.value == 'conversation_redirect_cycle'


@pytest.mark.parametrize('order', [('missing', 'donor'), ('donor', 'missing')])
def test_redirect_into_missing_document_blocks_even_if_it_is_also_a_source(order):
    rows = {'donor': {'deleted': True, 'sync_merged_into': 'missing'}}
    for _ in range(4):  # Set iteration order must not decide the outcome.
        with pytest.raises(BatchPrivacyBlocked) as blocked:
            fence(Client(rows), list(order))
        assert blocked.value.reason.value == 'conversation_redirect_missing'


def test_missing_plain_source_is_allowed_as_before():
    assert fence(Client({}), ['not-yet-created']) == 0


def test_over_budget_distinct_documents_still_block():
    rows = {f'live-{n}': {} for n in range(257)}
    with pytest.raises(BatchPrivacyBlocked) as blocked:
        fence(Client(rows), list(rows))
    assert blocked.value.reason.value == 'conversation_fence_budget'
    rows.pop('live-256')
    assert fence(Client(rows), list(rows)) == 0


def test_single_chain_over_budget_still_blocks():
    rows = {f'hop-{n}': {'deleted': True, 'sync_merged_into': f'hop-{n + 1}'} for n in range(300)}
    rows['hop-300'] = {}
    with pytest.raises(BatchPrivacyBlocked) as blocked:
        fence(Client(rows), ['hop-0'])
    assert blocked.value.reason.value == 'conversation_fence_budget'


def test_snapshots_record_every_distinct_conversation():
    rows, sources = merge_cascade(donors=9, max_hops=4)
    snapshots = {}
    assert_batch_write_allowed(Client(rows), None, 'owner', conversation_ids=sources, snapshots=snapshots)
    assert set(snapshots['conversations']) == set(rows)
