"""Flight-packed pyannote stages: worker contract and serial equivalence.

The worker-level tests use deterministic model doubles and run everywhere.
The model-level tests need torch + pyannote.audio (the batch GPU image, or any
CPU venv with the pinned pyannote 4.0.3). They build randomly initialized
community-1 architectures, so no gated checkpoint or network is needed, and
compare the packed path against the unchanged serial pyannote calls.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from config.batch_pipeline_providers import ProviderConfig, provider_config
from diarizer.batch_pipeline import PipelineWorker
from diarizer import batch_pipeline_flight as flight
from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.errors import FatalGpuError

RATE = 16000


def item(key, seconds):
    return WorkItem(key, 'owner-' + key, 100, 'encrypted://' + key, seconds, Priority.FRESH)


def synthetic_audio(seconds, seed):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    voices = [
        np.sin(2 * np.pi * f * t) * (np.sin(2 * np.pi * r * t + p) > 0)
        for f, r, p in ((180, 0.21, 0.0), (310, 0.13, 1.7), (95, 0.31, 2.9))
    ]
    signal = 0.25 * sum(voices) + 0.02 * rng.standard_normal(len(t))
    return signal.astype(np.float32)


# ---- pure helpers -----------------------------------------------------------


def test_flight_groups_respect_budget_and_route_oversize_units_to_serial():
    groups, serial = flight.flight_groups([100, 900, 1000, 2500, 50, 1700], 1800)
    assert groups == [[0, 1], [2, 4], [5]]
    assert serial == [3]


def test_packed_batches_cross_owner_boundaries_in_order():
    batches = list(flight.packed_batches([3, 0, 2, 4], 4))
    assert batches == [[(0, 0), (0, 1), (0, 2), (2, 0)], [(2, 1), (3, 0), (3, 1), (3, 2)], [(3, 3)]]


def test_only_allocator_exhaustion_is_recoverable():
    class OutOfMemoryError(RuntimeError):
        pass

    assert flight.is_out_of_memory(OutOfMemoryError('CUDA out of memory. Tried to allocate'))
    try:
        try:
            raise RuntimeError('CUDA out of memory')
        except RuntimeError as inner:
            raise MemoryError('batch_size (8) is probably too large') from inner
    except MemoryError as outer:
        assert flight.is_out_of_memory(outer)
    assert not flight.is_out_of_memory(RuntimeError('CUDA error: device-side assert triggered'))
    assert not flight.is_out_of_memory(ValueError('bad shape'))


def test_flight_knob_is_dark_until_explicitly_true(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_FLIGHT_BATCH_SECONDS', raising=False)
    assert ProviderConfig().flight_batching is False
    config = provider_config()
    assert config.flight_batching is False and config.flight_batch_seconds == 1800
    for value in ('false', '0', 'yes', 'on', ''):
        monkeypatch.setenv('BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED', value)
        assert provider_config().flight_batching is False
    monkeypatch.setenv('BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED', 'True')
    monkeypatch.setenv('BATCH_PIPELINE_FLIGHT_BATCH_SECONDS', '600')
    config = provider_config()
    assert config.flight_batching is True and config.flight_batch_seconds == 600
    for invalid in (0, -1, 7201, float('inf')):
        with pytest.raises(ValueError, match='flight batch budget'):
            ProviderConfig(flight_batch_seconds=invalid)


def test_mismatched_cached_embeddings_recompute_serially_instead_of_failing():
    original_calls = []
    diarizer = SimpleNamespace(
        _segmentation=SimpleNamespace(),
        get_segmentations=lambda file, hook=None: 'serial-segmentation',
        get_embeddings=lambda file, segmentation, exclude_overlap=False, hook=None: original_calls.append(file)
        or 'serial-embeddings',
    )
    flight.FlightPyannote(diarizer, SimpleNamespace(_segmentation=SimpleNamespace()), budget_seconds=1800)
    binarized = SimpleNamespace(data=np.zeros((4, 10, 3)))
    matching = {flight.EMBEDDINGS_KEY: np.zeros((4, 3, 256))}
    assert diarizer.get_embeddings(matching, binarized) is matching[flight.EMBEDDINGS_KEY]
    mismatched = {flight.EMBEDDINGS_KEY: np.zeros((5, 3, 256))}
    assert diarizer.get_embeddings(mismatched, binarized) == 'serial-embeddings'
    assert original_calls == [mismatched]
    assert diarizer.get_segmentations({}) == 'serial-segmentation'
    assert diarizer.get_segmentations({flight.SEGMENTATION_KEY: 'cached'}) == 'cached'


def test_model_doubles_disable_packing_instead_of_failing_startup():
    fake = SimpleNamespace(_segmentation=SimpleNamespace(model=object()))
    assert flight.FlightPyannote.create(fake, fake, budget_seconds=1800) is None


# ---- worker contract ----------------------------------------------------------


@pytest.fixture(autouse=True)
def full_unit_diarization(monkeypatch):
    # Packed diarization applies to full-unit diarization; speech-only
    # compaction is covered separately below.
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'false')


class Words:
    def transcribe_batch(self, samples):
        return [[{'word': 'hello', 'timestamp': [0.1, 0.2]}] for _ in samples]


def serial_vad(samples):
    # Deterministic stand-in for the segmentation-derived VAD.
    seconds = len(samples) / RATE
    return [(0.0, round(seconds * 0.75, 3))]


def serial_diarize(samples):
    seconds = len(samples) / RATE
    return {'turns': [{'start': 0.0, 'end': round(seconds / 2, 3), 'speaker': 'SPEAKER_00'}], 'backend': 'pyannote'}


class FakeFlight:
    """Same math as the serial doubles, but packed: one call per flight."""

    def __init__(self, *, segment_error=None, diarize_error=None, item_error_for=None, oversize=None):
        self.calls = []
        self.segment_error, self.diarize_error = segment_error, diarize_error
        self.item_error_for, self.oversize = item_error_for, oversize or set()

    def segment(self, samples_list):
        self.calls.append(('segment', [len(s) for s in samples_list]))
        if self.segment_error:
            raise self.segment_error
        return [None if len(s) in self.oversize else ('features', len(s)) for s in samples_list]

    def vad_spans(self, samples, features):
        assert features == ('features', len(samples))
        self.calls.append(('vad_spans', len(samples)))
        return serial_vad(samples)

    def diarize_many(self, entries):
        self.calls.append(('diarize_many', [(len(s), f is not None) for s, f in entries]))
        if self.diarize_error:
            raise self.diarize_error
        return [
            ValueError('one unit failed') if len(s) == self.item_error_for else serial_diarize(s) for s, _ in entries
        ]


def run(worker_flight, durations, *, vad=serial_vad, diarize=serial_diarize):
    saved, serial_calls = {}, []

    def counted_vad(samples):
        serial_calls.append(('vad', len(samples)))
        return vad(samples)

    def counted_diarize(samples):
        serial_calls.append(('diarize', len(samples)))
        return diarize(samples)

    def persist(work, payload):
        saved[work.segment_id] = payload
        return 'encrypted-result://' + work.segment_id

    worker = PipelineWorker(
        language_of=lambda item: 'en',
        decode=lambda work: synthetic_audio(work.duration_seconds, 7),
        vad=counted_vad,
        words_providers={'parakeet': Words()},
        diarizers={'pyannote': counted_diarize},
        persist=persist,
        flight_models=worker_flight,
    )
    results = worker.process_batch([item(k, s) for k, s in durations.items()])
    return results, saved, serial_calls


DURATIONS = {'a': 3.5, 'b': 12.25, 'c': 41.0}


def test_packed_flight_is_identical_to_serial_and_skips_serial_model_calls():
    serial_results, serial_saved, serial_calls = run(None, DURATIONS)
    packed = FakeFlight()
    packed_results, packed_saved, packed_serial_calls = run(packed, DURATIONS)
    assert sorted(serial_results, key=lambda r: r.segment_id) == sorted(packed_results, key=lambda r: r.segment_id)
    assert packed_saved == serial_saved and len(serial_saved) == 3
    assert len(serial_calls) == 6 and packed_serial_calls == []
    assert [c[0] for c in packed.calls] == ['segment', 'vad_spans', 'vad_spans', 'vad_spans', 'diarize_many']
    assert packed.calls[-1][1] == [(int(s * RATE), True) for s in DURATIONS.values()]


def test_oversize_unit_takes_serial_vad_but_still_diarizes_in_flight():
    oversize = int(DURATIONS['c'] * RATE)
    _, serial_saved, _ = run(None, DURATIONS)
    packed = FakeFlight(oversize={oversize})
    _, packed_saved, serial_calls = run(packed, DURATIONS)
    assert packed_saved == serial_saved
    assert serial_calls == [('vad', oversize)]
    assert (oversize, False) in packed.calls[-1][1]


@pytest.mark.parametrize('stage', ['segment', 'diarize'])
def test_non_fatal_flight_failure_falls_back_to_serial_path(stage):
    _, serial_saved, serial_calls = run(None, DURATIONS)
    error = RuntimeError('synthetic packed failure')
    packed = FakeFlight(**{f'{stage}_error': error})
    results, packed_saved, fallback_calls = run(packed, DURATIONS)
    assert packed_saved == serial_saved and all(isinstance(r, WorkResult) for r in results)
    expected = 'vad' if stage == 'segment' else 'diarize'
    assert [c for c in fallback_calls if c[0] == expected] == [c for c in serial_calls if c[0] == expected]


@pytest.mark.parametrize('stage', ['segment', 'diarize'])
def test_fatal_cuda_error_in_flight_quarantines_chain(stage):
    packed = FakeFlight(**{f'{stage}_error': RuntimeError('CUDA error: an illegal memory access was encountered')})
    with pytest.raises(FatalGpuError):
        run(packed, DURATIONS)


def test_per_unit_diarization_failure_only_fails_that_unit():
    failing = int(DURATIONS['b'] * RATE)
    results, saved, _ = run(FakeFlight(item_error_for=failing), DURATIONS)
    assert {r.segment_id for r in results} == {'a', 'c'} and set(saved) == {'a', 'c'}


def test_speech_only_diarization_keeps_its_serial_compacted_call(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'true')
    packed = FakeFlight()
    results, saved, serial_calls = run(packed, DURATIONS)
    assert {r.segment_id for r in results} == set(DURATIONS)
    # Packed segmentation still feeds VAD; diarization never uses full-unit
    # packed embeddings for a compacted waveform.
    assert [c[0] for c in packed.calls if c[0] == 'diarize_many'] == []
    assert [c[0] for c in serial_calls] == ['diarize'] * len(DURATIONS)


def test_silence_skips_packed_diarization():
    packed = FakeFlight()
    packed.vad_spans = lambda samples, features: []
    results, saved, _ = run(packed, DURATIONS)
    assert {r.outcome for r in results} == {'silence'}
    assert not [c for c in packed.calls if c[0] == 'diarize_many']


# ---- real pyannote equivalence (CPU) --------------------------------------------


@pytest.fixture
def pyannote_pair(tmp_path_factory):
    # Function scope: FlightPyannote installs hooks on the pipeline, so every
    # test needs a fresh, unpatched instance for its serial references.
    torch = pytest.importorskip('torch')
    pytest.importorskip('pyannote.audio')
    from pyannote.audio.core.plda import PLDA
    from pyannote.audio.core.task import Problem, Resolution, Specifications
    from pyannote.audio.models.embedding import WeSpeakerResNet34
    from pyannote.audio.models.segmentation import PyanNet
    from pyannote.audio.pipelines import SpeakerDiarization, VoiceActivityDetection

    torch.manual_seed(0)
    segmentation = PyanNet(sample_rate=RATE)
    segmentation.specifications = Specifications(
        problem=Problem.MONO_LABEL_CLASSIFICATION,
        resolution=Resolution.FRAME,
        duration=10.0,
        min_duration=10.0,
        warm_up=(0.0, 0.0),
        classes=['speaker#1', 'speaker#2', 'speaker#3'],
        powerset_max_classes=2,
        permutation_invariant=True,
    )
    segmentation.build()
    segmentation.eval()
    with torch.no_grad():
        # A random classifier is bias-dominated (one powerset class everywhere).
        # Sharpen it so local-speaker activity, counting and masks vary.
        segmentation.classifier.weight.mul_(60.0)
        segmentation.classifier.bias.zero_()
    embedding = WeSpeakerResNet34(sample_rate=RATE).eval()

    root = tmp_path_factory.mktemp('plda')
    rng = np.random.default_rng(0)
    lda = np.linalg.qr(rng.standard_normal((256, 256)))[0][:, :128]
    np.savez(root / 'xvec_transform.npz', mean1=np.zeros(256), mean2=np.zeros(128), lda=lda)
    tr = np.linalg.qr(rng.standard_normal((128, 128)))[0]
    np.savez(root / 'plda.npz', mu=np.zeros(128), tr=tr, psi=np.linspace(5.0, 0.1, 128))
    plda = PLDA(root / 'xvec_transform.npz', root / 'plda.npz')

    diarizer = SpeakerDiarization(
        segmentation=segmentation,
        embedding=embedding,
        plda=plda,
        clustering='VBxClustering',
        embedding_exclude_overlap=True,
        segmentation_batch_size=8,
        embedding_batch_size=8,
    )
    diarizer.instantiate(
        {'segmentation': {'min_duration_off': 0.0}, 'clustering': {'threshold': 0.6, 'Fa': 0.07, 'Fb': 0.8}}
    )
    # Same composition as batch_pipeline_startup.load_worker.
    vad = VoiceActivityDetection(segmentation=diarizer._segmentation.model)
    vad.instantiate({'min_duration_on': 0.0, 'min_duration_off': 0.0})
    vad._segmentation.batch_size = 8
    return torch, diarizer, vad


def test_packed_segmentation_vad_and_diarization_match_serial_pyannote(pyannote_pair):
    torch, diarizer, vad = pyannote_pair
    from diarizer.batch_pipeline_flight_qualify import _SpeechOnly
    from diarizer.batch_pipeline_models import PyannoteDiarizer, PyannoteVAD

    # Below one window, exact window multiple, ragged tails and multi-batch units.
    clips = [synthetic_audio(s, i) for i, s in enumerate((3.5, 10.0, 12.25, 21.5))]
    files = [{'waveform': torch.from_numpy(c).unsqueeze(0), 'sample_rate': RATE} for c in clips]
    speech_only = _SpeechOnly(diarizer)
    # Every serial reference is taken on the unpatched pipeline, before create.
    serial_vad = [PyannoteVAD(vad)(c) for c in clips]
    serial_diarization = [PyannoteDiarizer(diarizer)(c) for c in clips]
    serial_compacted = [speech_only(c, spans) for c, spans in zip(clips, serial_vad)]
    serial_segmentation = [diarizer._segmentation(f) for f in files]
    speaking = [
        i
        for i, seg in enumerate(serial_segmentation)
        if np.nanmax(diarizer.speaker_count(seg, diarizer._segmentation.model.receptive_field, warm_up=(0.0, 0.0)).data)
        > 0
    ]
    serial_embeddings = {
        i: diarizer.get_embeddings(files[i], serial_segmentation[i], exclude_overlap=True) for i in speaking
    }
    original_get_embeddings = diarizer.get_embeddings

    packed = flight.FlightPyannote.create(diarizer, vad, budget_seconds=1800)
    assert packed is not None and packed.shared_trunk
    assert diarizer.get_embeddings is not original_get_embeddings  # hooks now installed
    features = packed.segment(clips)
    assert all(f is not None for f in features)
    for feature, reference in zip(features, serial_segmentation):
        assert feature.segmentation.data.shape == reference.data.shape
        window, expected = feature.segmentation.sliding_window, reference.sliding_window
        assert (window.start, window.duration, window.step) == (expected.start, expected.duration, expected.step)
        np.testing.assert_allclose(feature.segmentation.data, reference.data, rtol=0, atol=1e-5)
    packed_vad = [packed.vad_spans(c, f) for c, f in zip(clips, features)]
    assert packed_vad == serial_vad

    # Cross-unit packed shared trunk vs pyannote's per-pair serial forward.
    assert len(speaking) >= 2
    shared = packed.embed_group([files[i] for i in speaking], [features[i].segmentation for i in speaking])
    for i, value in zip(speaking, shared):
        np.testing.assert_array_equal(np.isnan(value), np.isnan(serial_embeddings[i]))
        np.testing.assert_allclose(value, serial_embeddings[i], rtol=0, atol=1e-4, equal_nan=True)

    # Production composition (speech-only on): packed VAD, then the worker's
    # compacted diarization through the per-file shared-trunk hook.
    assert [speech_only(c, spans) for c, spans in zip(clips, packed_vad)] == serial_compacted
    # Speech-only off: full-unit packed diarization.
    assert sum(len(d['turns']) for d in serial_diarization) > 20
    assert packed.diarize_many(list(zip(clips, features))) == serial_diarization
    # Over-budget units fall back to the fully serial calls with the same output.
    tight = flight.FlightPyannote(diarizer, vad, budget_seconds=5)
    assert tight.segment(clips)[1:] == [None] * 3
    assert tight.diarize_many([(c, None) for c in clips]) == serial_diarization


def test_packed_out_of_memory_falls_back_to_serial_pyannote(pyannote_pair, monkeypatch):
    _, diarizer, vad = pyannote_pair
    from diarizer.batch_pipeline_models import PyannoteDiarizer

    clips = [synthetic_audio(s, i) for i, s in enumerate((12.25, 26.0))]
    serial = [PyannoteDiarizer(diarizer)(c) for c in clips]
    packed = flight.FlightPyannote(diarizer, vad, budget_seconds=1800)
    features = packed.segment(clips)

    class OutOfMemoryError(RuntimeError):
        pass

    def exhausted(*args, **kwargs):
        raise OutOfMemoryError('CUDA out of memory. Tried to allocate 2.00 GiB')

    monkeypatch.setattr(packed, 'embed_group', exhausted)
    assert packed.diarize_many(list(zip(clips, features))) == serial
    monkeypatch.setattr(packed, '_segment_group', exhausted)
    assert packed.segment(clips) == [None, None]
    # Packed group, then each unit's per-file shared trunk, then segmentation:
    # every OOM lands on pyannote's own serial calls.
    assert packed.counts['oom_fallbacks'] == 4
