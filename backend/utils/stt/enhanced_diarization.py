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
import wave
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Handle Pyannote imports with proper error handling
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
        self.audio_buffer = []
        self.segment_buffer = []
        self.speaker_mapping = {}
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
                
            # Use the latest Pyannote model
            model_name = os.getenv('PYANNOTE_MODEL', 'pyannote/speaker-diarization-3.0')
            
            logger.info(f"Initializing Pyannote pipeline: {model_name}")
            try:
                self.pipeline = Pipeline.from_pretrained(
                    model_name,
                    use_auth_token=hf_token
                )
            except Exception as e:
                logger.warning(f"Main model failed ({e}), trying alternative...")
                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization@3.0",
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
    
    def add_audio_chunk(self, audio_chunk: bytes, segments: List[Dict]) -> List[Dict]:
        """
        Add audio chunk and segments to buffer for processing.
        
        Args:
            audio_chunk: Raw audio bytes
            segments: List of segment dictionaries from Deepgram
            
        Returns:
            List of enhanced segment dictionaries
        """
        # Add to buffers
        self.audio_buffer.append(audio_chunk)
        self.segment_buffer.extend(segments)
        
        # Process if buffer is full enough (every 5 chunks or 10 seconds)
        if len(self.audio_buffer) >= 5:
            return self._process_buffered_audio()
        
        # Return original segments for now
        return segments
    
    def _process_buffered_audio(self) -> List[Dict]:
        """
        Process buffered audio with Pyannote for enhanced diarization.
        
        Returns:
            List of enhanced segment dictionaries
        """
        if not self.is_initialized or not self.audio_buffer or not self.segment_buffer:
            return self.segment_buffer
        
        try:
            # Combine audio chunks
            combined_audio = b''.join(self.audio_buffer)
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                self._save_audio_to_wav(combined_audio, tmp_file.name)
                
                # Process with Pyannote
                logger.info("Processing buffered audio with Pyannote")
                diarization = self.pipeline(tmp_file.name)
                
                # Map Pyannote results to Deepgram segments
                enhanced_segments = self._map_pyannote_to_deepgram(self.segment_buffer, diarization)
                
                # Clear buffers
                self.audio_buffer.clear()
                self.segment_buffer.clear()
                
                logger.info(f"Enhanced {len(enhanced_segments)} segments with Pyannote")
                return enhanced_segments
                
        except Exception as e:
            logger.error(f"Pyannote processing failed: {e}")
            # Return original segments on failure
            return self.segment_buffer
        finally:
            # Clean up temporary file
            if 'tmp_file' in locals():
                try:
                    os.unlink(tmp_file.name)
                except:
                    pass
    
    def _save_audio_to_wav(self, audio_data: bytes, file_path: str):
        """Save raw audio bytes to WAV file."""
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)  # 16kHz
            wav_file.writeframes(audio_data)
    
    def _map_pyannote_to_deepgram(self, segments: List[Dict], diarization) -> List[Dict]:
        """
        Map Pyannote speaker assignments to Deepgram segments using overlap analysis.
        
        This preserves Deepgram's excellent transcription while improving speaker assignments.
        """
        enhanced_segments = []
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
                if dominant_speaker not in self.speaker_mapping:
                    self.speaker_mapping[dominant_speaker] = f"SPEAKER_{next_speaker_id:02d}"
                    next_speaker_id += 1
                
                new_speaker = self.speaker_mapping[dominant_speaker]
            else:
                # No overlap found, keep original assignment
                new_speaker = segment.get('speaker', 'SPEAKER_00')
            
            # Create enhanced segment preserving all Deepgram data
            enhanced_segment = segment.copy()
            enhanced_segment['speaker'] = new_speaker
            
            # Update speaker_id for consistency
            if 'speaker_id' not in enhanced_segment:
                try:
                    enhanced_segment['speaker_id'] = int(new_speaker.split('_')[1])
                except (IndexError, ValueError):
                    enhanced_segment['speaker_id'] = 0
            
            enhanced_segments.append(enhanced_segment)
        
        return enhanced_segments
    
    def process_audio_file(self, audio_path: str, segments: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        Process complete audio file with Pyannote for post-processing.
        
        Args:
            audio_path: Path to audio file
            segments: Original segments from Deepgram
            
        Returns:
            Tuple of (enhanced_segments, metrics)
        """
        if not self.is_initialized:
            logger.warning("Enhanced diarization not available - returning original segments")
            return segments, {"status": "disabled", "improvement": 0}
        
        if not segments:
            logger.warning("No segments provided for enhancement")
            return segments, {"status": "no_segments", "improvement": 0}
        
        try:
            start_time = time.time()
            
            # Run Pyannote diarization on the audio file
            logger.info(f"Running enhanced diarization on {audio_path}")
            diarization = self.pipeline(audio_path)
            
            # Map Pyannote results to Deepgram segments
            enhanced_segments = self._map_pyannote_to_deepgram(segments, diarization)
            
            # Apply post-processing for consistency
            enhanced_segments = self._post_process_consistency(enhanced_segments)
            
            # Calculate improvement metrics
            metrics = self._calculate_metrics(segments, enhanced_segments)
            metrics["processing_time"] = time.time() - start_time
            metrics["status"] = "success"
            
            logger.info(f"Enhanced diarization completed in {metrics['processing_time']:.2f}s")
            logger.info(f"Speaker consistency improved by {metrics.get('consistency_improvement', 0):.1f}%")
            
            return enhanced_segments, metrics
            
        except Exception as e:
            logger.error(f"Enhanced diarization failed: {e}")
            return segments, {"status": "error", "error": str(e), "improvement": 0}
    
    def _post_process_consistency(self, segments: List[Dict]) -> List[Dict]:
        """
        Post-process segments to fix brief speaker switches and improve consistency.
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
                # Update speaker_id if present
                if 'speaker_id' in prev_segment:
                    processed_segments[i]['speaker_id'] = prev_segment['speaker_id']
        
        return processed_segments
    
    def _calculate_metrics(self, original: List[Dict], enhanced: List[Dict]) -> Dict:
        """Calculate improvement metrics comparing original vs enhanced diarization."""
        if not original or not enhanced:
            return {"improvement": 0}
        
        # Count speaker transitions
        original_transitions = self._count_speaker_transitions(original)
        enhanced_transitions = self._count_speaker_transitions(enhanced)
        
        # Count unique speakers
        original_speakers = len(set(seg.get('speaker', 'SPEAKER_00') for seg in original))
        enhanced_speakers = len(set(seg.get('speaker', 'SPEAKER_00') for seg in enhanced))
        
        # Calculate consistency improvement
        consistency_improvement = 0
        if original_transitions > 0:
            consistency_improvement = max(0, (original_transitions - enhanced_transitions) / original_transitions * 100)
        
        return {
            "original_speakers": original_speakers,
            "enhanced_speakers": enhanced_speakers,
            "original_transitions": original_transitions,
            "enhanced_transitions": enhanced_transitions,
            "consistency_improvement": consistency_improvement,
            "improvement": consistency_improvement
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

def apply_enhanced_diarization_to_segments(segments: List[Dict]) -> List[Dict]:
    """
    Apply enhanced diarization to real-time segments.
    
    This function provides a simple interface for real-time processing.
    """
    if not is_enhanced_diarization_enabled():
        return segments
    
    if not PYANNOTE_AVAILABLE:
        logger.warning("Pyannote not available - returning original segments")
        return segments
    
    try:
        enhanced_diarizer = get_enhanced_diarization()
        if not enhanced_diarizer.is_initialized:
            logger.warning("Enhanced diarization not initialized - returning original segments")
            return segments
        
        # For real-time, we can only do basic post-processing
        # Full Pyannote processing requires audio buffering
        enhanced_segments = enhanced_diarizer._post_process_consistency(segments)
        
        logger.info(f"Applied basic enhanced diarization to {len(segments)} segments")
        return enhanced_segments
    
    except Exception as e:
        logger.error(f"Enhanced diarization failed: {e}")
        return segments
