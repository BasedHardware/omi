SOURCE_SIGNAL_CAPTURE_PRIORS = {
    'typed': 0.95,
    'manual': 0.95,
    'push_to_talk': 0.9,
    'integration': 0.8,
    'transcription': 0.65,
    'background_transcription': 0.55,
    'ocr': 0.45,
    'legacy': 0.6,
    'unknown': 0.5,
}

VERACITY_PRIORS = {
    'base': 0.35,
    'single_independent_group': 0.45,
    'additional_independent_group': 0.22,
    'high_capture_bonus': 0.08,
    'low_capture_penalty': 0.12,
    'third_party_penalty': 0.08,
    'maximum': 0.98,
}

CONFIDENCE_BANDS = {
    'low': 0.0,
    'medium': 0.5,
    'high': 0.75,
    'certain': 0.9,
}

LOW_CAPTURE_THRESHOLD = 0.5
HIGH_CAPTURE_THRESHOLD = 0.85
