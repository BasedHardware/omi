"""
Speaker Identification Module for Omi Backend

Replaces regex-based speaker detection with a self-hosted LLM approach.
Identifies who the user is talking TO (addressees) vs. who is merely mentioned.

Fix for: https://github.com/BasedHardware/omi/issues/3039

Usage:
    from backend.utils.speaker_identification import identify_speaker_from_transcript
    
    result = identify_speaker_from_transcript("Hey Alice and Bob, can you help?")
    # Returns: ["Alice", "Bob"]
    
    result = identify_speaker_from_transcript("I told Alice about the meeting")
    # Returns: None
"""

import contextlib
import io
import json
import logging
import os
import threading
from typing import Optional

# ============================================================================
# Configuration
# ============================================================================
MODEL_PATH = os.environ.get(
    "SPEAKER_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "qwen_1.5b_speaker.gguf")
)
CONTEXT_WINDOW = 1024
GPU_LAYERS = -1  # Full GPU offload (Metal/CUDA), falls back to CPU automatically

logger = logging.getLogger(__name__)

# Thread-safe singleton
_model_instance = None
_model_lock = threading.Lock()

# ============================================================================
# System Prompt
# ============================================================================
SYSTEM_PROMPT = """You identify WHO is being directly SPOKEN TO (addressees) in a transcript.

ADDRESSED (return their names):
- "Hey Alice, can you help?" → ["Alice"]
- "Alice can you help me" → ["Alice"] (no comma, still addressed)
- "John, Bob, come here!" → ["John", "Bob"]
- "Hey Alice and Bob, listen up" → ["Alice", "Bob"]
- "What do you think, Jennifer?" → ["Jennifer"]
- "Listen Marcus, this matters" → ["Marcus"]

NOT ADDRESSED (return null):
- "I told Alice to stop" → null (talked ABOUT Alice)
- "Bob said he would come" → null (Bob is subject)
- "Did you hear what Sarah did?" → null (talking ABOUT Sarah)
- "Can you pass the salt?" → null (no name)

RULES:
1. Return names ONLY if someone is directly spoken TO
2. Names with comma separation = addressed
3. Names followed by imperative/question = addressed (even without comma)
4. Names as subject/object = NOT addressed
5. Multiple addressees → return all names
6. No addressee → return null

Respond with JSON: {"speakers": ["Name1", "Name2"]} or {"speakers": null}"""


# ============================================================================
# Model Loading (Thread-Safe Singleton)
# ============================================================================
def get_model():
    """
    Get the model singleton, loading if necessary.
    Thread-safe with suppressed initialization noise.
    Includes warmup to eliminate cold-start penalty.
    """
    global _model_instance
    
    if _model_instance is not None:
        return _model_instance
    
    with _model_lock:
        if _model_instance is not None:
            return _model_instance
        
        _model_instance = _load_model_silent()
        _warmup()
        
        return _model_instance


def _load_model_silent():
    """Load model with suppressed stderr noise."""
    if not os.path.exists(MODEL_PATH):
        logger.error(f"Model not found: {MODEL_PATH}")
        raise FileNotFoundError(
            f"Speaker ID model not found at {MODEL_PATH}. "
            "Download: curl -L -o qwen_1.5b_speaker.gguf "
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        )
    
    try:
        from llama_cpp import Llama
    except ImportError as e:
        raise ImportError("pip install llama-cpp-python") from e
    
    logger.info(f"Loading speaker ID model: {MODEL_PATH}")
    
    # Suppress Metal/CUDA initialization spam
    stderr_capture = io.StringIO()
    with contextlib.redirect_stderr(stderr_capture):
        model = Llama(
            model_path=MODEL_PATH,
            n_ctx=CONTEXT_WINDOW,
            n_gpu_layers=GPU_LAYERS,
            verbose=False,
            chat_format="chatml",
        )
    
    logger.info("Speaker ID model loaded successfully")
    return model


def _warmup():
    """Silent warmup inference to eliminate cold-start penalty."""
    try:
        identify_speaker_from_transcript("warmup", _warmup=True)
    except Exception:
        pass


# ============================================================================
# Main API Function
# ============================================================================
def identify_speaker_from_transcript(
    transcript: str,
    _warmup: bool = False
) -> Optional[list[str]]:
    """
    Identify who the user is talking TO in the given transcript.
    
    Args:
        transcript: The text to analyze.
        _warmup: Internal flag (do not use).
    
    Returns:
        List of addressed speaker names (e.g., ["Alice", "Bob"]),
        or None if no one is being directly addressed.
        
    Examples:
        >>> identify_speaker_from_transcript("Hey Alice, can you help?")
        ['Alice']
        >>> identify_speaker_from_transcript("Alice and Bob, come here!")
        ['Alice', 'Bob']
        >>> identify_speaker_from_transcript("I told Alice about it")
        None
    """
    model = get_model()
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f'Transcript: "{transcript}"'}
    ]
    
    try:
        # Suppress inference noise
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            response = model.create_chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=100,
                temperature=0.0,
            )
        
        content = response["choices"][0]["message"]["content"]
        result = json.loads(content)
        speakers = result.get("speakers")
        
        # Normalize
        if speakers is None or speakers == [] or speakers == "null":
            return None
        
        if isinstance(speakers, list):
            cleaned = [str(s).strip() for s in speakers if s]
            return cleaned if cleaned else None
        
        # Handle single string response
        if isinstance(speakers, str) and speakers.lower() != "null":
            return [speakers.strip()]
        
        return None
        
    except json.JSONDecodeError as e:
        if not _warmup:
            logger.warning(f"JSON parse error: {e}")
        return None
    except Exception as e:
        if not _warmup:
            logger.error(f"Speaker ID error: {e}")
        return None


# ============================================================================
# Legacy Compatibility (drop-in replacement for old function name)
# ============================================================================
def detect_speaker_from_text(text: str) -> Optional[str]:
    """
    Legacy function for backward compatibility.
    Returns only the first speaker name as a string.
    """
    speakers = identify_speaker_from_transcript(text)
    return speakers[0] if speakers else None
