import math
import pytest

from database.audio_timeline import (
    COVERAGE_TOLERANCE_SECONDS,
    chunk_span,
    group_chunks_by_coverage,
    parse_span_blob_metadata,
    span_blob_metadata,
)


class TestChunkSpanResilience:
    @pytest.mark.parametrize('bad_start', [float('nan'), float('inf'), float('-inf')])
    def test_chunk_span_rejects_non_finite_start(self, bad_start):
        chunk = {'span': {'start': bad_start, 'samples': 16000, 'sample_rate': 16000}}
        assert chunk_span(chunk) is None

    @pytest.mark.parametrize('bad_chunk', [None, '', 123, []])
    def test_chunk_span_rejects_non_mapping_chunk(self, bad_chunk):
        assert chunk_span(bad_chunk) is None

    def test_chunk_span_valid(self):
        chunk = {'span': {'start': 10.5, 'samples': 16000, 'sample_rate': 16000}}
        assert chunk_span(chunk) == {'start': 10.5, 'samples': 16000, 'sample_rate': 16000}


class TestSpanBlobMetadataResilience:
    @pytest.mark.parametrize('bad_start', [float('nan'), float('inf'), float('-inf')])
    def test_span_blob_metadata_rejects_non_finite_start(self, bad_start):
        span = {'start': bad_start, 'samples': 16000, 'sample_rate': 16000}
        with pytest.raises(ValueError, match="Span values must be finite and positive"):
            span_blob_metadata(span)

    @pytest.mark.parametrize('bad_span', [None, '', 123, []])
    def test_span_blob_metadata_rejects_non_mapping(self, bad_span):
        with pytest.raises(ValueError, match="span must be a Mapping"):
            span_blob_metadata(bad_span)

    def test_span_blob_metadata_valid_roundtrip(self):
        span = {'start': 10.5, 'samples': 16000, 'sample_rate': 16000}
        meta = span_blob_metadata(span)
        assert meta['v2_start'] == '10.5'
        assert meta['v2_samples'] == '16000'
        assert meta['v2_sample_rate'] == '16000'
        rehydrated = parse_span_blob_metadata(meta)
        assert rehydrated == span


class TestParseSpanBlobMetadataResilience:
    @pytest.mark.parametrize('bad_start', ['nan', 'inf', '-inf', 'NaN', 'Infinity'])
    def test_parse_span_blob_metadata_rejects_non_finite_start(self, bad_start):
        meta = {'v2_start': bad_start, 'v2_samples': '16000', 'v2_sample_rate': '16000'}
        assert parse_span_blob_metadata(meta) is None

    @pytest.mark.parametrize('bad_meta', [None, '', 123, []])
    def test_parse_span_blob_metadata_rejects_non_mapping(self, bad_meta):
        assert parse_span_blob_metadata(bad_meta) is None


class TestGroupChunksByCoverageResilience:
    @pytest.mark.parametrize('bad_chunks', [None, '', 123, {'a': 1}])
    def test_group_chunks_by_coverage_rejects_non_list(self, bad_chunks):
        assert group_chunks_by_coverage(bad_chunks, gap_threshold=1.0) == []

    @pytest.mark.parametrize('bad_threshold', [float('nan'), float('inf'), float('-inf'), None, 'bad'])
    def test_group_chunks_by_coverage_clamps_invalid_gap_threshold_to_zero(self, bad_threshold):
        chunks_with_gap = [
            {'timestamp': 100.0, 'span': {'start': 0.0, 'samples': 16000, 'sample_rate': 16000}},
            {'timestamp': 100.5, 'span': {'start': 1.0, 'samples': 16000, 'sample_rate': 16000}},
        ]
        assert len(group_chunks_by_coverage(chunks_with_gap, gap_threshold=bad_threshold)) == 2

    def test_group_chunks_by_coverage_splits_on_corrupt_legacy_timestamps(self):
        chunks = [
            {'timestamp': 100.0},
            {'timestamp': 'malformed_string'},
            {'timestamp': None},
            {},
            {'timestamp': 105.0},
        ]
        groups = group_chunks_by_coverage(chunks, gap_threshold=2.0)
        assert len(groups) == 5

    def test_group_chunks_by_coverage_handles_non_mapping_elements(self):
        chunks = [
            {'timestamp': 100.0},
            'not_a_dict',
            None,
            {'timestamp': 101.0},
        ]
        groups = group_chunks_by_coverage(chunks, gap_threshold=2.0)
        assert len(groups) == 4
