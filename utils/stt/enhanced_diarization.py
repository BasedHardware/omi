"""
Enhanced Speaker Diarization with Pyannote

This module provides improved speaker diarization by augmenting Deepgram's transcription
with Pyannote.audio's superior diarization capabilities.

The goal is to reduce diarization error rate by at least 50% while preserving
Deepgram's excellent transcription quality.
"""

import os
import time
import logging
import tempfile
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter

# Handle NumPy compatibility
try:
    import numpy as np
    # Handle NumPy 2.0 compatibility
    if hasattr(np, 'nan'):
        np_nan = np.nan
    else:
        np_nan = np.NaN
except ImportError:
    np = None

try:
    import torch
    import torchaudio
    from pyannote.audio import Pipeline
    from pyannote.core import Segment, Annotation
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    logging.warning("Pyannote.audio not available. Enhanced diarization will be disabled.")

logger = logging.getLogger(__name__)


class EnhancedDiarization:
    """
    Enhanced speaker diarization using Pyannote.audio.
    
    Augments Deepgram's transcription with improved speaker assignments
    by leveraging Pyannote's state-of-the-art diarization models.
    """
    
    def __init__(self):
        self.pipeline = None
        self.is_initialized = False
        self._initialize_pipeline()
    
    def _initialize_pipeline(self):
        """Initialize Pyannote pipeline with proper error handling."""
        if not PYANNOTE_AVAILABLE:
            logger.warning("Pyannote not available - enhanced diarization disabled")
            return
            
        try:
            hf_token = os.getenv('HUGGINGFACE_ACCESS_TOKEN')
            if not hf_token:
                logger.warning("HUGGINGFACE_ACCESS_TOKEN not set - enhanced diarization disabled")
                return
                
            # Use the most accurate Pyannote model
            model_name = os.getenv('PYANNOTE_MODEL', 'pyannote/speaker-diarization-3.1')
            
            logger.info(f"Initializing Pyannote pipeline: {model_name}")
            self.pipeline = Pipeline.from_pretrained(
                model_name,
                use_auth_token=hf_token
            )
            
            # Configure for optimal performance
            if torch.cuda.is_available():
                self.pipeline = self.pipeline.to(torch.device("cuda"))
                logger.info("Enhanced diarization using GPU acceleration")
            else:
                logger.info("Enhanced diarization using CPU")
                
            self.is_initialized = True
            logger.info("Enhanced diarization pipeline initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Pyannote pipeline: {e}")
            self.is_initialized = False
    
    def improve_diarization(
        self, 
        audio_path: str, 
        deepgram_segments: List[Dict],
        min_speakers: int = None,
        max_speakers: int = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Improve Deepgram's diarization using Pyannote while preserving transcription.
        
        Args:
            audio_path: Path to audio file
            deepgram_segments: Original segments from Deepgram with transcription
            min_speakers: Minimum number of speakers (optional)
            max_speakers: Maximum number of speakers (optional)
            
        Returns:
            Tuple of (improved_segments, metrics)
        """
        if not self.is_initialized:
            logger.warning("Enhanced diarization not available - returning original segments")
            return deepgram_segments, {"status": "disabled", "improvement": 0}
        
        if not deepgram_segments:
            logger.warning("No segments provided for enhancement")
            return deepgram_segments, {"status": "no_segments", "improvement": 0}
        
        try:
            start_time = time.time()
            
            # Run Pyannote diarization on the audio file
            logger.info(f"Running enhanced diarization on {audio_path}")
            diarization = self.pipeline(
                audio_path, 
                min_speakers=min_speakers, 
                max_speakers=max_speakers
            )
            
            # Map Pyannote results to Deepgram segments
            improved_segments = self._map_pyannote_to_deepgram(deepgram_segments, diarization)
            
            # Apply post-processing for consistency
            improved_segments = self._post_process_consistency(improved_segments)
            
            # Calculate improvement metrics
            metrics = self._calculate_metrics(deepgram_segments, improved_segments)
            metrics["processing_time"] = time.time() - start_time
            metrics["status"] = "success"
            
            logger.info(f"Enhanced diarization completed in {metrics['processing_time']:.2f}s")
            logger.info(f"Speaker consistency improved by {metrics.get('consistency_improvement', 0):.1f}%")
            
            return improved_segments, metrics
            
        except Exception as e:
            logger.error(f"Enhanced diarization failed: {e}")
            return deepgram_segments, {"status": "error", "error": str(e), "improvement": 0}
    
    def _map_pyannote_to_deepgram(self, segments: List[Dict], diarization: Annotation) -> List[Dict]:
        """
        Map Pyannote speaker assignments to Deepgram segments using overlap analysis.
        
        This preserves Deepgram's excellent transcription while improving speaker assignments.
        """
        improved_segments = []
        speaker_mapping = {}  # Map Pyannote speakers to SPEAKER_XX format
        next_speaker_id = 0
        
        for segment in segments:
            start_time = float(segment['start'])
            end_time = float(segment['end'])
            
            # Find overlapping speakers from Pyannote
            overlapping_speakers = defaultdict(float)
            
            for pyannote_segment, _, pyannote_speaker in diarization.itertracks(yield_label=True):
                overlap_start = max(start_time, pyannote_segment.start)
                overlap_end = min(end_time, pyannote_segment.end)
                overlap_duration = max(0, overlap_end - overlap_start)
                
                if overlap_duration > 0:
                    overlapping_speakers[pyannote_speaker] += overlap_duration
            
            # Determine the dominant speaker for this segment
            if overlapping_speakers:
                # Use speaker with maximum overlap
                dominant_speaker = max(overlapping_speakers.items(), key=lambda x: x[1])[0]
                
                # Create consistent speaker mapping
                if dominant_speaker not in speaker_mapping:
                    speaker_mapping[dominant_speaker] = f"SPEAKER_{next_speaker_id:02d}"
                    next_speaker_id += 1
                
                new_speaker = speaker_mapping[dominant_speaker]
            else:
                # No overlap found, keep original assignment
                new_speaker = segment.get('speaker', 'SPEAKER_00')
            
            # Create improved segment preserving all Deepgram data
            improved_segment = segment.copy()
            improved_segment['speaker'] = new_speaker
            
            # Update speaker_id for consistency
            try:
                improved_segment['speaker_id'] = int(new_speaker.split('_')[1])
            except (IndexError, ValueError):
                improved_segment['speaker_id'] = 0
            
            improved_segments.append(improved_segment)
        
        return improved_segments
    
    def _post_process_consistency(self, segments: List[Dict]) -> List[Dict]:
        """
        Post-process segments to fix brief speaker switches and improve consistency.
        
        This addresses common diarization errors like brief mis-assignments.
        """
        if len(segments) < 3:
            return segments
        
        processed_segments = segments.copy()
        
        # Fix brief speaker switches (segments < 2 seconds surrounded by same speaker)
        for i in range(1, len(processed_segments) - 1):
            current = processed_segments[i]
            prev_segment = processed_segments[i - 1]
            next_segment = processed_segments[i + 1]
            
            # Check if current segment is a brief switch
            if (prev_segment['speaker'] == next_segment['speaker'] and 
                prev_segment['speaker'] != current['speaker'] and
                (current['end'] - current['start']) < 2.0):
                
                logger.debug(f"Fixing brief speaker switch at {current['start']:.1f}s")
                processed_segments[i]['speaker'] = prev_segment['speaker']
                processed_segments[i]['speaker_id'] = prev_segment['speaker_id']
        
        return processed_segments
    
    def _calculate_metrics(self, original: List[Dict], improved: List[Dict]) -> Dict:
        """Calculate improvement metrics comparing original vs improved diarization."""
        if not original or not improved:
            return {"improvement": 0}
        
        # Count speaker transitions
        original_transitions = self._count_speaker_transitions(original)
        improved_transitions = self._count_speaker_transitions(improved)
        
        # Count unique speakers
        original_speakers = len(set(seg.get('speaker', 'SPEAKER_00') for seg in original))
        improved_speakers = len(set(seg.get('speaker', 'SPEAKER_00') for seg in improved))
        
        # Calculate consistency improvement
        consistency_improvement = 0
        if original_transitions > 0:
            consistency_improvement = max(0, (original_transitions - improved_transitions) / original_transitions * 100)
        
        return {
            "original_speakers": original_speakers,
            "improved_speakers": improved_speakers,
            "original_transitions": original_transitions,
            "improved_transitions": improved_transitions,
            "consistency_improvement": consistency_improvement,
            "improvement": consistency_improvement  # Overall improvement score
        }
    
    def _count_speaker_transitions(self, segments: List[Dict]) -> int:
        """Count the number of speaker transitions in segments."""
        if len(segments) < 2:
            return 0
        
        transitions = 0
        for i in range(1, len(segments)):
            if segments[i].get('speaker') != segments[i-1].get('speaker'):
                transitions += 1
        
        return transitions


# Singleton instance for performance
_enhanced_diarization_instance = None

def get_enhanced_diarization() -> EnhancedDiarization:
    """Get singleton instance of enhanced diarization."""
    global _enhanced_diarization_instance
    if _enhanced_diarization_instance is None:
        _enhanced_diarization_instance = EnhancedDiarization()
    return _enhanced_diarization_instance


def is_enhanced_diarization_enabled() -> bool:
    """Check if enhanced diarization is enabled via environment variable."""
    return os.getenv('ENHANCED_DIARIZATION_ENABLED', 'false').lower() in ('true', '1', 'yes')
