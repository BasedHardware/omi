"""
Unit tests for speaker diarization module

Run with: python -m pytest backend/testing/test_speaker_diarization.py
Or: cd backend/testing && python test_speaker_diarization.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import torch
import numpy as np
from utils.stt.speaker_diarization import (
    _simple_kmeans,
    _compute_silhouette,
    _compute_wcss,
    _select_optimal_k,
)


def test_simple_kmeans_single_cluster():
    """Test k-means with K=1 returns all zeros"""
    X = torch.randn(10, 192)
    labels, centers = _simple_kmeans(X, K=1)
    
    assert labels.shape[0] == 10
    assert torch.all(labels == 0)
    assert centers.shape[0] == 1


def test_simple_kmeans_two_clusters():
    """Test k-means can separate two distinct clusters"""
    # Create two well-separated clusters
    cluster1 = torch.randn(20, 192) + torch.tensor([5.0] * 192)
    cluster2 = torch.randn(20, 192) - torch.tensor([5.0] * 192)
    X = torch.cat([cluster1, cluster2], dim=0)
    
    labels, centers = _simple_kmeans(X, K=2)
    
    assert labels.shape[0] == 40
    assert len(torch.unique(labels)) == 2
    assert centers.shape[0] == 2


def test_compute_silhouette_single_cluster():
    """Test silhouette score for single cluster is 0"""
    X = torch.randn(10, 192)
    labels = torch.zeros(10, dtype=torch.long)
    
    score = _compute_silhouette(X, labels, K=1)
    assert score == 0.0


def test_compute_silhouette_good_clustering():
    """Test silhouette score is positive for well-separated clusters"""
    cluster1 = torch.randn(20, 192) + torch.tensor([10.0] * 192)
    cluster2 = torch.randn(20, 192) - torch.tensor([10.0] * 192)
    X = torch.cat([cluster1, cluster2], dim=0)
    
    labels, _ = _simple_kmeans(X, K=2)
    score = _compute_silhouette(X, labels, K=2)
    
    assert score > 0.5  # Good clustering should have high silhouette


def test_compute_wcss():
    """Test WCSS calculation"""
    X = torch.randn(10, 192)
    labels = torch.zeros(10, dtype=torch.long)
    
    wcss = _compute_wcss(X, labels)
    assert wcss > 0
    assert isinstance(wcss, float)


def test_select_optimal_k_single_speaker():
    """Test optimal K selection for single speaker (low variance)"""
    # Create embeddings with very low variance (same speaker)
    X = torch.randn(10, 192) * 0.01  # Very small variance
    
    K, labels, centers = _select_optimal_k(X, max_k=6)
    
    assert K == 1
    assert torch.all(labels == 0)


def test_select_optimal_k_multiple_speakers():
    """Test optimal K selection for multiple speakers"""
    # Create 3 well-separated clusters
    cluster1 = torch.randn(10, 192) + torch.tensor([10.0] * 192)
    cluster2 = torch.randn(10, 192)
    cluster3 = torch.randn(10, 192) - torch.tensor([10.0] * 192)
    X = torch.cat([cluster1, cluster2, cluster3], dim=0)
    
    K, labels, centers = _select_optimal_k(X, max_k=6)
    
    # Should detect 2-4 clusters (BIC might be conservative)
    assert 2 <= K <= 4
    assert len(torch.unique(labels)) == K


def test_select_optimal_k_edge_case_one_sample():
    """Test optimal K selection with only one sample"""
    X = torch.randn(1, 192)
    
    K, labels, centers = _select_optimal_k(X, max_k=6)
    
    assert K == 1
    assert labels.shape[0] == 1


def test_integration_with_audio():
    """
    Integration test with real audio file
    
    To run this test:
    1. Place a test audio file at backend/testing/test_audio.wav
    2. Run: python test_speaker_diarization.py --integration
    
    Expected: Returns diarized segments with speaker labels
    """
    import os
    from utils.stt.speaker_diarization import diarize_segments
    from pydub import AudioSegment
    
    test_audio_path = os.path.join(os.path.dirname(__file__), 'test_audio.wav')
    
    if not os.path.exists(test_audio_path):
        print(f"⚠️  Skipping integration test (no test audio at {test_audio_path})")
        return
    
    # Load audio
    aseg = AudioSegment.from_wav(test_audio_path)
    duration = aseg.duration_seconds
    
    # Create mock segments (in production these come from transcription)
    mock_segments = [
        {
            'speaker': 'SPEAKER_0',
            'start': 0.0,
            'end': duration,
            'text': 'Integration test segment',
            'is_user': False,
            'person_id': None
        }
    ]
    
    # Run diarization
    diarized = diarize_segments(mock_segments, test_audio_path, duration)
    
    # Validate results
    assert len(diarized) > 0, "Should return segments"
    assert all('speaker' in seg for seg in diarized), "All segments should have speaker labels"
    assert all(seg['speaker'].startswith('SPEAKER_') for seg in diarized), "Speaker labels should be formatted correctly"
    
    print(f"✅ Integration test passed! Found {len(set(s['speaker'] for s in diarized))} speakers in {len(diarized)} segments")
    for speaker in sorted(set(s['speaker'] for s in diarized)):
        count = sum(1 for s in diarized if s['speaker'] == speaker)
        print(f"   {speaker}: {count} segments")


if __name__ == "__main__":
    import sys
    
    print("Running speaker diarization tests...")
    test_simple_kmeans_single_cluster()
    test_simple_kmeans_two_clusters()
    test_compute_silhouette_single_cluster()
    test_compute_silhouette_good_clustering()
    test_compute_wcss()
    test_select_optimal_k_single_speaker()
    test_select_optimal_k_multiple_speakers()
    test_select_optimal_k_edge_case_one_sample()
    print("✅ All unit tests passed!")
    
    if '--integration' in sys.argv:
        print("\nRunning integration test...")
        test_integration_with_audio() 