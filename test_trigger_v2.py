def test_question_after_trigger():
    # The ACTUAL implementation from the file
    def question_after_trigger(text: str) -> str:
        import re
        # Note: In the real file, these are raw strings or properly escaped
        match = re.search(r'hey[ ,]+omi\b', text) or re.search(r'\bomi\b', text)
        return text[match.end():].strip(' \t\n\r,') if match else ''

    test_cases = [
        ("hey omi, what time is it", "what time is it"),
        ("hey omi what time is it", "what time is it"),
        ("Hey Omi what is the weather", "what is the weather"),
        ("hello omi how are you", "how are you"),
        ("just some text", ""),
        ("omi, help me", "help me"),
        ("omi help me", "help me"),
        ("hey   omi  where am i", "where am i"),
    ]

    print("Running tests for question_after_trigger...")
    failed = 0
    for text, expected in test_cases:
        actual = question_after_trigger(text.lower())
        if actual == expected:
            print(f"✅ PASS: '{text}' -> '{actual}'")
        else:
            print(f"❌ FAIL: '{text}' | Expected: '{expected}' | Actual: '{actual}'")
            failed += 1
    
    if failed == 0:
        print("\nAll tests passed!")
    else:
        print(f"\n{failed} tests failed.")
    return failed

if __name__ == "__main__":
    test_question_after_trigger()
