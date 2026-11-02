"""#23792: quoted matches and correction IO must honor the recall boundary."""

from copy import deepcopy
from types import SimpleNamespace

from google.api_core.exceptions import DeadlineExceeded
import pytest

from database import conversations, review_store, transcript_search as store
from database.conversations import prepare_conversation_for_read
from database.firestore_retry import FIRESTORE_NO_RETRY
from tests.unit.test_direct_transcript_search import data
from utils.agent_capabilities import transcripts
from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted
from utils.retrieval.tool_services import transcript_search as service


def test_long_neighbor_cannot_displace_the_actual_matching_segment(data):
    rows, _ = data
    rows[0]['transcript_segments'] = [
        {'text': 'Invoice routing note. ' + 'Unrelated preface. ' * 300, 'start': 0, 'end': 100, 'is_user': False},
        {'text': 'The invoice total was 47 dollars.', 'start': 100, 'end': 103, 'is_user': False},
    ]
    sources = []
    result = service.search_saved_transcripts_text('u1', 'invoice total', limit=1, source_sink=sources)
    assert sources[0]['source_id'] == 'c000'
    assert 'invoice total was 47 dollars' in result
    assert 'invoice total was 47 dollars' in sources[0]['preview']


def test_correction_overlay_read_receives_the_transcript_deadline(data, monkeypatch):
    rows, _ = data
    rows[0]['has_transcript_corrections'] = True
    calls = []

    class CorrectionClient:
        def collection(self, name):
            assert name in ('users', 'transcript_corrections')
            return self

        def document(self, name):
            assert name in ('u1', 'c000')
            return self

        def get(self, **kwargs):
            calls.append(kwargs)
            return self

        def to_dict(self):
            return None

    def prepare(value, uid, **kwargs):
        # Preserve the production caller's budget while substituting only IO.
        kwargs['firestore_client'] = CorrectionClient()
        return prepare_conversation_for_read(value, uid, **kwargs)

    monkeypatch.setattr(store, 'prepare_conversation_for_read', prepare)
    service.search_saved_transcripts_text('u1', 'invoice', limit=1)
    assert len(calls) == 1
    assert 0 < calls[0].get('timeout', 0) <= 4


@pytest.mark.parametrize('prefix', ['Invoice note. ' * 200, 'Ｉｎｖｏｉｃｅ note. ' * 200], ids=['ascii', 'nfkc'])
def test_crop_finds_complete_phrase_in_center_instead_of_earlier_partial_term(prefix):
    text = prefix + 'The invoice total was 47 dollars.'
    result = build_transcript_match_snippets([{'text': text}], 'invoice total', max_chars=180, center_match=True)
    assert len(result) == 1
    assert 'The invoice total was 47 dollars.' in result[0]['text']
    assert len(result[0]['text']) <= 180


@pytest.mark.parametrize('max_chars', [1, 6, 80])
def test_crop_without_all_matching_terms_is_not_evidence(max_chars):
    result = build_transcript_match_snippets(
        [{'text': 'Invoice ' + 'Unrelated preface. ' * 100 + 'total was 47 dollars.'}],
        'invoice total',
        max_chars=max_chars,
        center_match=True,
    )
    assert result == []


def test_rejected_crop_does_not_suppress_the_next_matching_center():
    result = build_transcript_match_snippets(
        [
            {'text': 'Invoice ' + 'Unrelated preface. ' * 100 + 'total.'},
            {'text': 'The invoice total was 47 dollars.'},
            {'text': 'Long following context. ' * 200},
        ],
        'invoice total',
        max_chars=180,
        center_match=True,
    )
    assert len(result) == 1
    assert 'The invoice total was 47 dollars.' in result[0]['text']


class OverlayClient:
    """Only IO is substituted: production codec, correction projection and budgets run."""

    def __init__(self, raw, overlay, clock, *, refuse=False):
        self.raw, self.overlay, self.clock, self.refuse = raw, overlay, clock, refuse
        self.calls = []

    def collection(self, name):
        return OverlayRef(self, (name,))

    def get_all(self, refs, **kwargs):
        assert [ref.path for ref in refs] == [('users', 'u1', 'conversations', 'c000')]
        self.clock[0] = 3.25  # The primary read consumed most of the original four seconds.
        return [SimpleNamespace(exists=True, id='c000', to_dict=lambda: deepcopy(self.raw))]


class OverlayRef:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def collection(self, name):
        return OverlayRef(self.client, (*self.path, name))

    document = collection

    def get(self, **kwargs):
        assert self.path == ('users', 'u1', 'transcript_corrections', 'c000')
        self.client.calls.append(kwargs)
        if self.client.refuse:
            raise DeadlineExceeded('synthetic correction deadline')
        return SimpleNamespace(exists=True, to_dict=lambda: deepcopy(self.client.overlay))


@pytest.fixture
def corrected_recall(data, monkeypatch):
    rows, query = data

    def setup(*, level, refuse=False):
        clock = [0.0]
        captured = deepcopy(rows[0])
        captured['transcript_segments'][0]['id'] = 'segment-one'
        captured.update(data_protection_level=level, has_transcript_corrections=True)
        overlay = review_store.encode_doc(
            'u1',
            {
                'source': [
                    dict(
                        undone=False,
                        segment_index=0,
                        segment_id='segment-one',
                        start=0,
                        kind='transcript',
                        before='The invoice total was 47 dollars.',
                        after='The invoice total was 83 dollars.',
                    )
                ]
            },
        )
        raw = conversations.encode_conversation_for_write('u1', captured, level)
        rows[:] = [raw]
        client = OverlayClient(raw, overlay, clock, refuse=refuse)
        query.on_read = lambda row: clock.__setitem__(0, 3.25)
        monkeypatch.setattr(conversations, 'db', client)
        monkeypatch.setattr(review_store, 'client', lambda: client)
        monkeypatch.setattr(
            store,
            'prepare_conversation_for_read',
            lambda value, uid, **kwargs: prepare_conversation_for_read(
                value, uid, **{**kwargs, 'firestore_client': client}
            ),
        )
        monkeypatch.setattr(
            service,
            'ListReadBudget',
            SimpleNamespace(
                for_request=lambda *args, **kwargs: ListReadBudget.for_request(*args, **kwargs, clock=lambda: clock[0])
            ),
        )
        return client

    return setup


@pytest.mark.parametrize('exact', [False, True], ids=['scan', 'exact'])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_both_projection_paths_use_remaining_deadline_and_current_corrected_text(corrected_recall, exact, level):
    client = corrected_recall(level=level)
    captured = deepcopy(client.raw)
    sources = []
    result = service.search_saved_transcripts_text(
        'u1', 'invoice total', conversation_id='c000' if exact else None, source_sink=sources
    )
    assert len(client.calls) == 1
    assert client.calls[0]['timeout'] == pytest.approx(0.75)
    assert client.calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert '83 dollars' in result and '47 dollars' not in result
    assert len(sources) == 1 and '83 dollars' in sources[0]['preview']
    assert client.raw == captured


@pytest.mark.parametrize('exact', [False, True], ids=['scan', 'exact'])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_correction_deadline_cannot_fall_back_to_original_text_or_register_evidence(corrected_recall, exact, level):
    client = corrected_recall(level=level, refuse=True)
    sources = []
    result = service.search_saved_transcripts_text(
        'u1', 'invoice total', conversation_id='c000' if exact else None, source_sink=sources
    )
    assert len(client.calls) == 1 and client.calls[0]['timeout'] == pytest.approx(0.75)
    assert sources == []
    assert '47 dollars' not in result and '83 dollars' not in result
    assert 'deadline' in result or 'unavailable' in result


@pytest.mark.parametrize('bounded', [False, True])
def test_overlay_transaction_keeps_its_transaction_and_optional_read_budget(bounded):
    client = OverlayClient({}, review_store.encode_doc('u1', {'source': []}), [0.0])
    transaction = object()
    budget = ListReadBudget.for_request(None, route='test', seconds=4) if bounded else None
    assert (
        transcripts.load_entries('u1', 'c000', firestore_client=client, transaction=transaction, read_budget=budget)
        == []
    )
    assert client.calls[0]['transaction'] is transaction
    assert ('timeout' in client.calls[0]) is bounded
    if bounded:
        assert client.calls[0]['retry'] is FIRESTORE_NO_RETRY and budget.docs_scanned == 1


def test_expired_budget_starts_no_correction_rpc():
    client = OverlayClient({}, {}, [0.0])
    budget = ListReadBudget(deadline_monotonic=0, clock=lambda: 0)
    with pytest.raises(ListReadBudgetExhausted):
        transcripts.load_entries('u1', 'c000', firestore_client=client, read_budget=budget)
    assert client.calls == []
