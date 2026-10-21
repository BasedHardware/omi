"""Half-open send provenance, compared with the pinned R8 mapper and a sample oracle."""

import json
import os
from pathlib import Path
import random
from typing import List, Optional, Tuple

import pytest

from utils.audio_timeline import SendMap


# Frozen defect oracle from a091158c90000e89d1c138d055fbf019f4376c3b.
# Keep this independent of the candidate method; CI needs no historical Git objects.
class BaseSendMap(SendMap):
    def map_interval(self, provider_first_sample: int, provider_last_sample: int) -> Optional[Tuple[int, int]]:
        """Translate a provider interval to capture samples.

        Each endpoint maps independently through its containing span, so a
        segment is never mapped *through* an unrepresented gap as if it were
        audio. Endpoints outside every accepted span (beyond edge tolerance)
        reject with None rather than landing on another epoch — and so does an
        interval whose two different provider times would clamp onto one
        capture sample: that collapse fabricates a zero-length segment at a
        span edge instead of mapping the speech, so it fails closed too.
        """
        if provider_last_sample < provider_first_sample:
            provider_first_sample, provider_last_sample = provider_last_sample, provider_first_sample
        start_capture = self.map_sample(provider_first_sample)
        if start_capture is None:
            return None
        end_capture = self.map_sample(provider_last_sample)
        if end_capture is None:
            return None
        # Provider time is continuous across VAD-skipped capture audio. The
        # endpoints alone can therefore enclose a capture gap which was never
        # sent. Keep the whole text unplaced instead of inventing that window.
        previous: Optional[List[int]] = None
        for span in self._spans:
            provider_from, _, length = span
            if provider_from >= provider_last_sample:
                break
            if provider_from + length < provider_first_sample:
                continue
            if previous is not None and previous[1] + previous[2] != span[1]:
                return None
            previous = span
        if provider_last_sample > provider_first_sample and end_capture <= start_capture:
            return None
        return (start_capture, end_capture)


@pytest.fixture(scope="module")
def base_mapper():
    return BaseSendMap.map_interval


def sample_oracle(spans, first, end):
    """Enumerate only samples actually sent for [first,end), independently of endpoints."""
    samples = []
    for provider in range(first, end):
        matches = [capture + provider - start for start, capture, length in spans if start <= provider < start + length]
        if len(matches) != 1:
            return None
        samples.extend(matches)
    if not samples or any(right != left + 1 for left, right in zip(samples, samples[1:])):
        return None
    return samples[0], samples[-1] + 1


@pytest.mark.parametrize('seed', range(24))
def test_randomized_compact_maps_preserve_every_correct_base_window(base_mapper, seed):
    rng = random.Random(seed)
    counts = dict(compared=0, correct_base=0, changed=0, shortened=0, refused=0, newly_proven=0)
    shapes = ['contiguous', 'vad_gap', 'duplicate', 'reorder']
    for _ in range(16):
        sends = SendMap(1)  # zero edge tolerance: integer-sample provenance
        capture, length = rng.randrange(10, 30), rng.randrange(2, 9)
        sends.add_accepted_spans([(capture, length)])
        for shape in rng.sample(shapes, len(shapes)):
            previous = sends._spans[-1]
            capture = previous[1] + previous[2]
            if shape == 'vad_gap':
                capture += rng.randrange(1, 10)
            elif shape == 'duplicate':
                capture = previous[1]
            elif shape == 'reorder':
                capture = max(0, previous[1] - rng.randrange(1, 10))
            sends.add_accepted_spans([(capture, rng.randrange(2, 9))])
        total = sends.last_provider_sample
        assert total is not None
        # Exhaust ALL integer windows in each randomized map, including every
        # boundary as a start/end, one-sample intervals and entire-span crossings.
        for first in range(total):
            for end in range(first + 1, total + 1):
                base = base_mapper(sends, first, end)
                candidate = sends.map_interval(first, end)
                oracle = sample_oracle(sends._spans, first, end)
                counts['compared'] += 1
                if base is not None and base == oracle:
                    counts['correct_base'] += 1
                    assert candidate == base
                if candidate is not None:
                    assert candidate == oracle
                if base != candidate:
                    counts['changed'] += 1
                    # Only exact exclusive ends at a discontinuous compact
                    # boundary change. Non-boundary windows retain base output.
                    index = next(i for i, span in enumerate(sends._spans) if span[0] + span[2] == end)
                    assert index + 1 < len(sends._spans)
                    previous, following = sends._spans[index : index + 2]
                    assert previous[1] + previous[2] != following[1]
                    assert base != oracle  # never alter a previously correct accepted window
                    if candidate is None:
                        counts['refused'] += 1
                    elif base is None:
                        counts['newly_proven'] += 1
                    else:
                        assert candidate[0] == base[0] and candidate[1] < base[1]
                        counts['shortened'] += 1
    assert counts['changed'] and counts['correct_base']
    output = os.getenv('SEND_MAP_R9_PROPERTY_OUTPUT')
    if output:
        Path(f'{output}.{seed}.json').write_text(json.dumps(counts, sort_keys=True) + '\n')


@pytest.mark.parametrize('next_capture', [20, 0, 5])
def test_end_before_gap_duplicate_or_reorder(next_capture):
    sends = SendMap(10)
    sends.add_accepted_spans([(0, 10), (next_capture, 10)])
    assert sends.map_interval(2, 10) == (2, 10)
    assert sends.map_interval(2, 11) is None
    assert sends.map_interval(2, 20) is None


def test_provider_hole_with_adjacent_capture_still_refuses():
    sends = SendMap(10)
    sends.add_accepted(0, 0, 10)
    sends.add_accepted(20, 10, 10)
    assert sends.map_interval(2, 10) == (2, 10)
    assert sends.map_interval(2, 25) is None


def test_existing_outer_tolerance_and_point_semantics():
    sends = SendMap(100)
    sends.add_accepted_spans([(0, 100), (200, 100)])
    assert sends.map_sample(100) == 200  # inclusive point still belongs to next span
    assert sends.map_interval(-1, 100) == (0, 100)
    assert sends.map_interval(101, 201) == (201, 300)
    assert sends.map_interval(201, 202) is None
    assert sends.map_interval(100, 100) == (200, 200)
