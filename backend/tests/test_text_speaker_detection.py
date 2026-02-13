
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from utils.text_speaker_detection import (
    detect_speaker_from_text,
    identify_speaker_and_clean_transcript,
    identify_speaker_from_transcript,
)

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
    # 2. LLM ADDRESSEE DETECTION TESTS (Mocked - Async)
    # --------------------------------------------------------------------------
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("transcript, mock_response, expected_speakers", [
        ("Hey Alice", '{"speakers": ["Alice"], "cleaned_transcript": "Hey Alice"}', ["Alice"]),
        ("I told Alice", '{"speakers": null, "cleaned_transcript": "I told Alice"}', None),
    ])
    async def test_llm_addressee_detection(self, transcript, mock_response, expected_speakers):
        """Verify that identify_speaker_from_transcript handles OpenAI response correctly."""
        print(f"\n[Test] Input: '{transcript}'")
        print(f"[Test] Mock Output: {mock_response}")
        
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = mock_response
        
        with patch('utils.text_speaker_detection.get_async_client', new_callable=AsyncMock) as mock_get_client:
            mock_client_instance = MagicMock()
            mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get_client.return_value = mock_client_instance
            
            result = await identify_speaker_from_transcript(transcript)
            print(f"[Test] Parsed Result: {result}")
            assert result == expected_speakers

    @pytest.mark.asyncio
    async def test_llm_full_response_structure(self):
        """Verify that identify_speaker_and_clean_transcript returns full structure."""
        print("\n[Test] Checking Full JSON Structure...")
        
        mock_response = '{"speakers": ["Alice"], "cleaned_transcript": "Cleaned text"}'
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = mock_response
        
        with patch('utils.text_speaker_detection.get_async_client', new_callable=AsyncMock) as mock_get_client:
            mock_client_instance = MagicMock()
            mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get_client.return_value = mock_client_instance
            
            result = await identify_speaker_and_clean_transcript("input text")
            print(f"[Test] Result: {result}")
            assert result["speakers"] == ["Alice"]
            assert result["cleaned_transcript"] == "Cleaned text"

    @pytest.mark.asyncio
    async def test_llm_api_failure(self):
        """Verify graceful fallback when API fails."""
        print("\n[Test] Simulating API Failure (500/Timeout)...")
        
        with patch('utils.text_speaker_detection.get_async_client', new_callable=AsyncMock) as mock_get_client:
            mock_client_instance = MagicMock()
            mock_client_instance.chat.completions.create = AsyncMock(side_effect=Exception("API Down"))
            mock_get_client.return_value = mock_client_instance
            
            transcript = "Raw text"
            result = await identify_speaker_and_clean_transcript(transcript)
            print(f"[Test] Fallback Result: {result}")
            
            assert result["speakers"] is None
            assert result["cleaned_transcript"] == transcript

    @pytest.mark.asyncio
    async def test_llm_invalid_json(self):
        """Verify fallback when LLM returns invalid JSON."""
        print("\n[Test] Simulating Invalid JSON (Hallucination)...")
        
        mock_response = 'Not JSON!'
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = mock_response
        
        with patch('utils.text_speaker_detection.get_async_client', new_callable=AsyncMock) as mock_get_client:
            mock_client_instance = MagicMock()
            mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get_client.return_value = mock_client_instance
            
            transcript = "Raw text"
            result = await identify_speaker_and_clean_transcript(transcript)
            print(f"[Test] Fallback Result: {result}")
            
            assert result["speakers"] is None
            assert result["cleaned_transcript"] == transcript

    def test_empty_input(self):
        """Verify empty input returns None immediately without API call."""
        print("\n[Test] Checking Empty Input...")
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(identify_speaker_and_clean_transcript(""))
        loop.close()
        print(f"[Test] Early Return Result: {result}")
        
        assert result["speakers"] is None
        assert result["cleaned_transcript"] == ""

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
