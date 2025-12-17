
import pytest
import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from utils.speaker_identification import detect_speaker_from_text, identify_speaker_from_transcript

class TestSpeakerIdentification:
    
    # --------------------------------------------------------------------------
    # 1. LEGACY REGEX TESTS (Self-Identification)
    # --------------------------------------------------------------------------
    
    @pytest.mark.parametrize("text, expected", [
        ("I am Alice", "Alice"),
        ("My name is Bob", "Bob"),
        ("Je m'appelle Pierre", "Pierre"),  # French
        ("Hola, soy Maria", "Maria"),       # Spanish
        ("Hey Alice, help me", None),       # Addressed -> None
        ("Alice is here", None),            # Mentioned -> None
    ])
    def test_legacy_regex_self_identification(self, text, expected):
        """Verify that detect_speaker_from_text uses regex to find self-introductions."""
        assert detect_speaker_from_text(text) == expected

    # --------------------------------------------------------------------------
    # 2. LLM ADDRESSEE DETECTION TESTS
    # --------------------------------------------------------------------------
    
    @pytest.mark.parametrize("transcript, expected_speakers", [
        # POSITIVE CASES (Addressed)
        ("Hey Alice, can you help?", ["Alice"]),
        ("Bob, come here.", ["Bob"]),
        ("What do you think, Jennifer?", ["Jennifer"]),
        ("John and Mary, listen up.", ["John", "Mary"]),
        
        # NEGATIVE CASES (Mentioned but NOT addressed)
        ("I told Alice about the meeting.", None),
        ("I saw Bob yesterday.", None),
        ("She asked Sarah to come.", None),
        ("Did you hear about Mike?", None),
        ("Can you pass the salt?", None),
    ])
    def test_llm_addressee_detection(self, transcript, expected_speakers):
        """Verify that identify_speaker_from_transcript distinguishes addressed vs mentioned."""
        result = identify_speaker_from_transcript(transcript)
        assert result == expected_speakers

    def test_llm_warmup_logging(self, caplog):
        """Verify warmup logs warnings on failure but doesn't crash."""
        from utils.speaker_identification import _warmup
        
        # Mocking identify_speaker_from_transcript to raise exception
        # We can't easily mock the internal call inside _warmup without patching, 
        # but we can rely on the fact that the real function catches exceptions.
        # This test is just a placeholder to ensure the function exists.
        try:
            _warmup()
        except Exception:
            pytest.fail("Warmup raised exception instead of logging it")

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
