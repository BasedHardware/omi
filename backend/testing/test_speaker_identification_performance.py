#!/usr/bin/env python3
"""
Performance tests for Speaker Name Identification with NER
"""

import time
import pytest
from utils.speaker_identification import detect_speaker_from_text

class TestSpeakerIdentificationPerformance:
    """Performance tests for speaker identification"""
    
    def test_ner_performance(self):
        """Test NER performance with various text lengths"""
        test_cases = [
            ("Hi, I'm Alice.", "en", "Alice"),
            ("My name is Bob and I'll be your guide today.", "en", "Bob"),
            ("Hello everyone, I'm Alice and I'll be explaining the process today.", "en", "Alice"),
            ("Hola, me llamo Carlos y soy el doctor.", "es", "Carlos"),
            ("Bonjour, je suis Marie.", "fr", "Marie"),  # Changed to direct introduction
            ("我是王伟。", "zh", "王伟"),  # Changed to direct introduction
        ]
        
        for text, lang, expected in test_cases:
            start_time = time.time()
            result = detect_speaker_from_text(text, lang)
            end_time = time.time()
            
            # Performance assertion: should complete in under 20 seconds (first run includes model loading)
            assert (end_time - start_time) < 20.0, f"NER processing took too long: {end_time - start_time:.2f}s"
            
            if expected:
                assert result is not None, f"Expected {expected}, got None for text: {text}"
                assert expected in result, f"Expected {expected} in result {result} for text: {text}"
    
    def test_multilingual_performance(self):
        """Test performance across multiple languages"""
        languages = ["en", "es", "fr", "zh"]
        test_text = "Hi, I'm Alice."
        
        for lang in languages:
            start_time = time.time()
            result = detect_speaker_from_text(test_text, lang)
            end_time = time.time()
            
            # Performance assertion: should complete in under 20 seconds (first run includes model loading)
            assert (end_time - start_time) < 20.0, f"Language {lang} processing took too long: {end_time - start_time:.2f}s"
    
    def test_fallback_performance(self):
        """Test fallback to regex performance"""
        # Test with text that should trigger regex fallback
        test_cases = [
            "Let's get started with the meeting.",
            "The weather is nice today.",
            "This is a test without names.",
        ]
        
        for text in test_cases:
            start_time = time.time()
            result = detect_speaker_from_text(text, "en")
            end_time = time.time()
            
            # Performance assertion: should complete in under 0.1 seconds for regex
            assert (end_time - start_time) < 0.1, f"Regex fallback took too long: {end_time - start_time:.2f}s"
            assert result is None, f"Expected None for text without names: {text}"
    
    def test_concurrent_access(self):
        """Test thread safety and concurrent access"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def worker(text, lang, expected):
            result = detect_speaker_from_text(text, lang)
            results.put((text, lang, expected, result))
        
        # Create multiple threads
        threads = []
        test_cases = [
            ("Hi, I'm Alice.", "en", "Alice"),
            ("Hola, me llamo Carlos.", "es", "Carlos"),
            ("Je m'appelle Marie.", "fr", "Marie"),
            ("我是王伟。", "zh", "王伟"),
        ]
        
        for text, lang, expected in test_cases:
            thread = threading.Thread(target=worker, args=(text, lang, expected))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        while not results.empty():
            text, lang, expected, result = results.get()
            if expected:
                assert result is not None, f"Expected {expected}, got None for text: {text}"
                assert expected in result, f"Expected {expected} in result {result} for text: {text}"
    
    def test_memory_usage(self):
        """Test memory usage doesn't grow excessively"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Process many texts
        for i in range(100):
            detect_speaker_from_text(f"Hi, I'm Alice{i}.", "en")
        
        final_memory = process.memory_info().rss
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (less than 100MB)
        assert memory_growth < 100 * 1024 * 1024, f"Memory growth too high: {memory_growth / 1024 / 1024:.2f}MB"
