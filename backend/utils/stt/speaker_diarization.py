"""
Speaker diarization using ECAPA-TDNN embeddings and clustering.
"""
import os
import numpy as np
import torch
import webrtcvad
from typing import List, Dict, Tuple
from pydub import AudioSegment
from speechbrain.inference.speaker import EncoderClassifier


# Global embedding model
_ECAPA_MODEL = None


def _get_ecapa_model():
    """Lazy-load ECAPA-TDNN model once"""
    global _ECAPA_MODEL
    if _ECAPA_MODEL is None:
        _ECAPA_MODEL = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb"
        )
    return _ECAPA_MODEL


def _vad_split_segments(segments: List[dict], wav_path: str, duration: float) -> List[dict]:
    """
    Split segments using WebRTC VAD to find precise speech boundaries.
    Only splits at natural sentence breaks with significant pauses.
    """
    vad = webrtcvad.Vad(2)
    aseg = AudioSegment.from_wav(wav_path)
    sample_rate = 16000
    frame_duration_ms = 30
    frame_size = int(sample_rate * frame_duration_ms / 1000)
    
    # Convert audio to 16-bit PCM
    raw_audio = aseg.raw_data
    audio_samples = np.frombuffer(raw_audio, dtype=np.int16)
    
    # Run VAD on 30ms frames
    vad_regions = []
    for i in range(0, len(audio_samples) - frame_size + 1, frame_size):
        frame = audio_samples[i:i + frame_size].tobytes()
        is_speech = vad.is_speech(frame, sample_rate)
        start_s = i / sample_rate
        end_s = (i + frame_size) / sample_rate
        if is_speech:
            if vad_regions and (start_s - vad_regions[-1][1]) < 0.15:
                vad_regions[-1] = (vad_regions[-1][0], end_s)
            else:
                vad_regions.append((start_s, end_s))
    
    # Filter: min 200ms duration, pad by 100ms
    filtered_vad = []
    for start, end in vad_regions:
        if (end - start) >= 0.2:
            padded_start = max(0.0, start - 0.1)
            padded_end = min(duration, end + 0.1)
            filtered_vad.append((padded_start, padded_end))
    
    def get_vad_overlap(seg_start: float, seg_end: float) -> List[Tuple[float, float]]:
        overlaps = []
        for vad_start, vad_end in filtered_vad:
            ov_start = max(seg_start, vad_start)
            ov_end = min(seg_end, vad_end)
            if ov_end > ov_start:
                overlaps.append((ov_start, ov_end))
        return overlaps
    
    # Split segments at VAD boundaries
    vad_split_segments = []
    for seg in segments:
        seg_start = float(seg['start'])
        seg_end = float(seg['end'])
        vad_overlaps = get_vad_overlap(seg_start, seg_end)
        
        # Only split if clear pause and natural sentence break
        should_split = False
        if len(vad_overlaps) > 1:
            text = seg.get('text', '').strip()
            split_indicators = ['. ', '? ', '! ', ', and ', ', but ', ', so ']
            has_natural_split = any(indicator in text for indicator in split_indicators)
            
            max_gap = 0.0
            for i in range(len(vad_overlaps) - 1):
                gap = vad_overlaps[i+1][0] - vad_overlaps[i][1]
                max_gap = max(max_gap, gap)
            
            should_split = has_natural_split and max_gap >= 0.3
        
        if not should_split:
            vad_split_segments.append(seg)
        else:
            text_words = seg['text'].split()
            total_dur = seg_end - seg_start
            words_allocated = 0
            for i, (vad_start, vad_end) in enumerate(vad_overlaps):
                vad_dur = vad_end - vad_start
                word_ratio = vad_dur / total_dur if total_dur > 0 else 0
                word_count = max(1, int(len(text_words) * word_ratio))
                
                if i == len(vad_overlaps) - 1:
                    seg_words = text_words[words_allocated:]
                else:
                    seg_words = text_words[words_allocated:words_allocated + word_count]
                    words_allocated += word_count
                
                vad_split_segments.append({
                    'speaker': seg['speaker'],
                    'start': vad_start,
                    'end': vad_end,
                    'text': ' '.join(seg_words).strip() if seg_words else '',
                    'is_user': seg['is_user'],
                    'person_id': seg['person_id'],
                })
    
    return [s for s in vad_split_segments if s.get('text', '').strip()]


def _extract_embedding(audio_segment: AudioSegment, start_s: float, end_s: float, model) -> torch.Tensor:
    """Extract ECAPA-TDNN embedding from audio segment"""
    start_ms = max(0, int(start_s * 1000))
    end_ms = max(start_ms + 1, int(end_s * 1000))
    seg_audio = audio_segment[start_ms:end_ms]
    
    # ECAPA needs min 1s, pad if needed
    min_duration_ms = 1000
    if (end_ms - start_ms) < min_duration_ms:
        center_ms = (start_ms + end_ms) // 2
        start_ms = max(0, center_ms - min_duration_ms // 2)
        end_ms = min(len(audio_segment), start_ms + min_duration_ms)
        seg_audio = audio_segment[start_ms:end_ms]
    
    # Convert to tensor
    samples = np.array(seg_audio.get_array_of_samples()).astype(np.float32)
    if seg_audio.channels > 1:
        samples = samples.reshape((-1, seg_audio.channels)).mean(axis=1)
    samples = samples / 32768.0
    waveform = torch.from_numpy(samples).unsqueeze(0)
    
    # Pad to min length
    if waveform.size(1) < 16000:
        pad_length = 16000 - waveform.size(1)
        waveform = torch.nn.functional.pad(waveform, (0, pad_length))
    
    # Extract embedding
    with torch.no_grad():
        embedding = model.encode_batch(waveform)
        if embedding.dim() == 3:
            embedding = embedding.squeeze(0).mean(dim=0)
        elif embedding.dim() == 2:
            embedding = embedding.mean(dim=0)
        else:
            embedding = embedding.squeeze()
    
    return torch.nn.functional.normalize(embedding, dim=0)


def _simple_kmeans(X: torch.Tensor, K: int) -> Tuple[torch.Tensor, torch.Tensor]:
    """Simple k-means clustering"""
    N = X.size(0)
    if K == 1:
        return torch.zeros(N, dtype=torch.long), X.mean(dim=0, keepdim=True)
    
    # Initialization: k-means++
    first_center = X[0]
    dists_from_first = torch.norm(X - first_center, dim=1)
    second_idx = torch.argmax(dists_from_first).item()
    centers = [first_center, X[second_idx]]
    
    for _ in range(2, K):
        min_dists = []
        for i in range(N):
            dists_to_centers = [torch.norm(X[i] - c).item() for c in centers]
            min_dists.append(min(dists_to_centers))
        next_idx = torch.tensor(min_dists).argmax().item()
        centers.append(X[next_idx])
    
    centers = torch.stack(centers)
    
    # K-means iterations
    for _ in range(20):
        dists = torch.norm(X.unsqueeze(1) - centers.unsqueeze(0), dim=2)
        labels = torch.argmin(dists, dim=1)
        
        new_centers = []
        for k in range(K):
            mask = (labels == k)
            if mask.any():
                new_centers.append(X[mask].mean(dim=0))
            else:
                new_centers.append(centers[k])
        new_centers = torch.stack(new_centers)
        
        if torch.allclose(centers, new_centers, atol=1e-4):
            break
        centers = new_centers
    
    return labels, centers


def _compute_silhouette(X: torch.Tensor, labels: torch.Tensor, K: int) -> float:
    """Compute silhouette score"""
    if K <= 1:
        return 0.0
    
    silhouette_scores = []
    for i in range(X.size(0)):
        same_cluster = (labels == labels[i])
        if same_cluster.sum() > 1:
            intra_dist = torch.norm(X[i].unsqueeze(0) - X[same_cluster], dim=1).mean().item()
        else:
            intra_dist = 0.0
        
        min_inter_dist = float('inf')
        for k in torch.unique(labels):
            if k != labels[i]:
                other_cluster = (labels == k)
                if other_cluster.sum() > 0:
                    inter_dist = torch.norm(X[i].unsqueeze(0) - X[other_cluster], dim=1).mean().item()
                    min_inter_dist = min(min_inter_dist, inter_dist)
        
        if min_inter_dist == float('inf'):
            silhouette_scores.append(0.0)
        else:
            s = (min_inter_dist - intra_dist) / max(min_inter_dist, intra_dist, 1e-8)
            silhouette_scores.append(s)
    
    return sum(silhouette_scores) / len(silhouette_scores)


def _compute_wcss(X: torch.Tensor, labels: torch.Tensor) -> float:
    """Compute within-cluster sum of squares"""
    if len(torch.unique(labels)) <= 1:
        return float('inf')
    
    wcss = 0.0
    for i in range(X.size(0)):
        cluster_id = labels[i].item()
        cluster_mask = (labels == cluster_id)
        if cluster_mask.sum() > 0:
            cluster_center = X[cluster_mask].mean(dim=0)
            dist_to_center = torch.norm(X[i] - cluster_center).item()
            wcss += dist_to_center ** 2
    
    return wcss


def _select_optimal_k(X: torch.Tensor, max_k: int = 6) -> Tuple[int, torch.Tensor, torch.Tensor]:
    """
    Select optimal number of clusters using BIC with silhouette validation.
    BIC (Bayesian Information Criterion) is the gold standard for model selection.
    """
    if X.size(0) < 2:
        return 1, torch.zeros(X.size(0), dtype=torch.long), X.mean(dim=0, keepdim=True)
    
    # Check embedding variation
    pairwise_dists = torch.cdist(X, X, p=2)
    mask = ~torch.eye(X.size(0), dtype=torch.bool)
    all_dists = pairwise_dists[mask]
    std_dist = all_dists.std().item()
    
    # Very low variation = single speaker
    if all_dists.max().item() < 0.1 or std_dist < 0.02:
        return 1, torch.zeros(X.size(0), dtype=torch.long), X.mean(dim=0, keepdim=True)
    
    # Try different K values
    results = {}
    for K in range(1, min(max_k + 1, X.size(0) + 1)):
        try:
            labels, centers = _simple_kmeans(X, K)
            wcss = _compute_wcss(X, labels)
            silhouette = _compute_silhouette(X, labels, K)
            
            results[K] = {
                'labels': labels,
                'centers': centers,
                'wcss': wcss,
                'silhouette': silhouette
            }
        except Exception:
            continue
    
    if not results:
        return 1, torch.zeros(X.size(0), dtype=torch.long), X.mean(dim=0, keepdim=True)
    
    # Compute BIC for each K
    N = X.size(0)
    D = X.size(1)
    bic_scores = {}
    
    for K in results.keys():
        wcss = results[K]['wcss']
        if wcss > 0:
            log_likelihood = -(N * D / 2) * torch.log(torch.tensor(wcss / N + 1e-10))
        else:
            log_likelihood = torch.tensor(float('-inf'))
        
        n_params = K * D + K
        bic = -2 * log_likelihood + n_params * torch.log(torch.tensor(float(N)))
        bic_scores[K] = bic.item()
    
    # Best K by BIC (minimum)
    bic_k = min(bic_scores.keys(), key=lambda k: bic_scores[k])
    
    # Validate with silhouette (> 0.15 = meaningful separation)
    valid_k_by_sil = [k for k in results.keys() if results[k]['silhouette'] > 0.15]
    
    if bic_k in valid_k_by_sil:
        final_k = bic_k
    elif valid_k_by_sil:
        final_k = max(valid_k_by_sil, key=lambda k: results[k]['silhouette'])
    else:
        final_k = bic_k
    
    # Sanity check for single speaker
    max_sil = max(r['silhouette'] for r in results.values())
    if max_sil < 0.1 and std_dist < 0.05:
        final_k = 1
    
    return final_k, results[final_k]['labels'], results[final_k]['centers']


def diarize_segments(segments: List[dict], wav_path: str, duration: float) -> List[dict]:
    """
    Perform speaker diarization on transcript segments using ECAPA-TDNN embeddings.
    
    Args:
        segments: List of transcript segments with 'text', 'start', 'end'
        wav_path: Path to 16kHz mono WAV file
        duration: Audio duration in seconds
    
    Returns:
        Updated segments with speaker labels (SPEAKER_0, SPEAKER_1, etc.)
    """
    if not segments:
        return segments
    
    try:
        model = _get_ecapa_model()
        audio = AudioSegment.from_wav(wav_path)
        
        # Split segments using VAD
        segments = _vad_split_segments(segments, wav_path, duration)
        
        # Extract embeddings
        embeddings = []
        valid_idx = []
        for i, seg in enumerate(segments):
            start_s = float(seg['start'])
            end_s = float(seg['end'])
            if end_s - start_s < 0.3 or not seg.get('text'):
                continue
            
            try:
                emb = _extract_embedding(audio, start_s, end_s, model)
                embeddings.append(emb)
                valid_idx.append(i)
            except Exception:
                continue
        
        if not embeddings:
            return segments
        
        # Cluster embeddings
        E = torch.stack(embeddings, dim=0)
        K, labels, _ = _select_optimal_k(E)
        
        # Assign cluster labels
        for idx, lab in zip(valid_idx, labels.tolist()):
            segments[idx]['cluster'] = int(lab)
            segments[idx]['speaker'] = f'SPEAKER_{int(lab)}'
        
        # Inherit labels for invalid segments
        last_lab = 0
        for i in range(len(segments)):
            if 'cluster' in segments[i]:
                last_lab = segments[i]['cluster']
            else:
                segments[i]['cluster'] = last_lab
                segments[i]['speaker'] = f'SPEAKER_{last_lab}'
        
        # Merge contiguous segments with same speaker
        max_merge_seconds = float(os.getenv('MAX_MERGE_SECONDS', '6'))
        merged = []
        for seg in segments:
            if merged and merged[-1]['speaker'] == seg['speaker']:
                if (float(seg['end']) - float(merged[-1]['start'])) <= max_merge_seconds:
                    merged[-1]['text'] = (merged[-1]['text'] + ' ' + seg['text']).strip()
                    merged[-1]['end'] = float(seg['end'])
                else:
                    merged.append(seg)
            else:
                merged.append(seg)
        
        return merged
    
    except Exception as e:
        print(f"Speaker diarization failed: {e}")
        return segments 