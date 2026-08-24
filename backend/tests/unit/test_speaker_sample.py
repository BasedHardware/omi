import asyncio

import pytest

import utils.speaker_sample as speaker_sample


def _make_words(texts, speakers=None):
    words = []
    for index, text in enumerate(texts):
        word = {"text": text}
        if speakers is not None:
            word["speaker"] = speakers[index]
        words.append(word)
    return words


def _make_speaker_cycle(counts):
    speakers = []
    for speaker, count in counts:
        speakers.extend([speaker] * count)
    return speakers


def test_verify_and_transcribe_sample_transcription_failure(monkeypatch):
    def fake_deepgram(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript is None
    assert is_valid is False
    assert isinstance(reason, str)
    assert reason != "ok"


def test_verify_and_transcribe_sample_insufficient_words(monkeypatch):
    words = _make_words(
        ["thanks", "for", "joining", "today"],
        speakers=["SPEAKER_00"] * 4,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript is None
    assert is_valid is False
    assert reason == f"insufficient_words: {len(words)}/{speaker_sample.MIN_WORDS}"


def test_verify_and_transcribe_sample_multi_speaker_ratio(monkeypatch):
    words = _make_words(
        ["hi", "everyone", "lets", "start", "now"],
        speakers=["SPEAKER_00", "SPEAKER_00", "SPEAKER_00", "SPEAKER_01", "SPEAKER_01"],
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript is None
    assert is_valid is False
    assert reason == "multi_speaker: ratio=0.60"


def test_verify_and_transcribe_sample_multi_speaker_ratio_just_below(monkeypatch):
    texts = [
        "pizza",
        "raccoons",
        "run",
        "faster",
        "at",
        "midnight",
        "probably",
        "maybe",
        "who",
        "knows",
        "honestly",
        "shrug",
        "today",
    ]
    speakers = [
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_01",
        "SPEAKER_01",
        "SPEAKER_01",
    ]
    words = _make_words(texts, speakers=speakers)

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript is None
    assert is_valid is False
    assert reason.startswith("multi_speaker: ratio=")


def test_verify_and_transcribe_sample_text_mismatch(monkeypatch):
    words = _make_words(
        ["good", "morning", "thanks", "for", "coming"],
        speakers=["SPEAKER_00"] * 5,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fake_containment(_text1, _text2):
        return 0.5

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fake_containment)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(
            b"audio", 16000, expected_text="good afternoon, appreciate you coming"
        )
    )

    assert transcript == "good morning thanks for coming"
    assert is_valid is False
    assert reason == "text_mismatch: containment=0.50"


def test_verify_and_transcribe_sample_text_mismatch_just_below(monkeypatch):
    words = _make_words(
        ["galaxy", "salsa", "makes", "the", "party", "loud"],
        speakers=["SPEAKER_00"] * 6,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fake_containment(_text1, _text2):
        return 0.89

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fake_containment)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(b"audio", 16000, expected_text="galaxy salsa party")
    )

    assert transcript == "galaxy salsa makes the party loud"
    assert is_valid is False
    assert reason == "text_mismatch: containment=0.89"


def test_verify_and_transcribe_sample_success(monkeypatch):
    words = _make_words(["thanks", "for", "joining", "the", "meeting"])

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fake_containment(_text1, _text2):
        return 0.95

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fake_containment)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(b"audio", 16000, expected_text="thanks for joining the meeting")
    )

    assert transcript == "thanks for joining the meeting"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_containment_real_function(monkeypatch):
    words = _make_words(
        ["orbiting", "satellites", "drift", "above", "quietly"],
        speakers=["SPEAKER_00"] * 5,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(
            b"audio", 16000, expected_text="today orbiting satellites drift above quietly"
        )
    )

    assert transcript == "orbiting satellites drift above quietly"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_minimum_word_boundary(monkeypatch):
    words = _make_words(
        ["party", "on", "planet", "pizza", "night"],
        speakers=["SPEAKER_00"] * 5,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript == "party on planet pizza night"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_dominant_ratio_boundary(monkeypatch):
    texts = [
        "unicorns",
        "love",
        "glitter",
        "and",
        "rainbows",
        "plus",
        "cosmic",
        "cupcakes",
        "today",
        "yay",
    ]
    speakers = _make_speaker_cycle([("SPEAKER_00", 7), ("SPEAKER_01", 3)])
    words = _make_words(texts, speakers=speakers)

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript == " ".join(texts)
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_containment_boundary(monkeypatch):
    words = _make_words(
        ["space", "pirates", "sail", "the", "neon", "seas"],
        speakers=["SPEAKER_00"] * 6,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fake_containment(_text1, _text2):
        return 0.9

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fake_containment)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(b"audio", 16000, expected_text="space pirates sail neon seas")
    )

    assert transcript == "space pirates sail the neon seas"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_uses_default_speaker(monkeypatch):
    words = _make_words(["just", "a", "solo", "astronaut", "report"])

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript == "just a solo astronaut report"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_empty_speaker_string(monkeypatch):
    words = _make_words(
        ["blank", "speaker", "tag", "shows", "up"],
        speakers=["", "", "", "", ""],
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript == "blank speaker tag shows up"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_skips_similarity_when_expected_missing(monkeypatch):
    words = _make_words(
        ["late", "night", "taco", "debate", "begins"],
        speakers=["SPEAKER_00"] * 5,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fail_similarity(*_args, **_kwargs):
        raise AssertionError("compute_text_containment should not be called")

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fail_similarity)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(b"audio", 16000, expected_text="")
    )

    assert transcript == "late night taco debate begins"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_skips_similarity_when_expected_none(monkeypatch):
    words = _make_words(
        ["cosmic", "karaoke", "night", "is", "legendary"],
        speakers=["SPEAKER_00"] * 5,
    )

    def fake_deepgram(*_args, **_kwargs):
        return words

    def fail_similarity(*_args, **_kwargs):
        raise AssertionError("compute_text_containment should not be called")

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)
    monkeypatch.setattr(speaker_sample, "compute_text_containment", fail_similarity)

    transcript, is_valid, reason = asyncio.run(
        speaker_sample.verify_and_transcribe_sample(b"audio", 16000, expected_text=None)
    )

    assert transcript == "cosmic karaoke night is legendary"
    assert is_valid is True
    assert reason == "ok"


def test_verify_and_transcribe_sample_empty_transcript(monkeypatch):
    def fake_deepgram(*_args, **_kwargs):
        return []

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", fake_deepgram)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert transcript is None
    assert is_valid is False
    assert reason == "insufficient_words: 0/5"


# --- provider granularity: the counts are over words, not over list entries ------------------------
#
# A transcriber may return either granularity, and both are legitimate. Deepgram emits one entry per
# word, so counting entries and counting words are the same number there. Parakeet emits one entry per
# SEGMENT with the whole utterance inside — measured against a live parakeet on a 24.9s sample, its
# /v2/transcribe response carries `segments: 1` and no `words` field at all. Counting entries therefore
# read 1, and every parakeet-backed sample was rejected as `insufficient_words` whatever it contained;
# the same miscount made the multi-speaker ratio 1.0 on a single entry, so that guard stopped rejecting
# instead of stopping bad samples.


def _make_segments(texts, speakers=None):
    """One entry per segment, each carrying several words — what parakeet returns."""
    segments = []
    for index, text in enumerate(texts):
        segment = {"text": text}
        if speakers is not None:
            segment["speaker"] = speakers[index]
        segments.append(segment)
    return segments


def test_a_single_segment_is_counted_by_its_words_not_as_one_entry(monkeypatch):
    segments = _make_segments(["hester prynne went one day to the mansion"], speakers=["SPEAKER_00"])

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", lambda *_a, **_k: segments)

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert (is_valid, reason) == (True, "ok")
    assert transcript == "hester prynne went one day to the mansion"


def test_word_granular_and_segment_granular_agree_on_the_same_utterance(monkeypatch):
    """The same eight words, split two ways, must produce the same verdict."""
    words = " one two three four five six seven eight".split()

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", lambda *_a, **_k: _make_words(words))
    per_word = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    monkeypatch.setattr(
        speaker_sample, "deepgram_prerecorded_from_bytes", lambda *_a, **_k: _make_segments([" ".join(words)])
    )
    per_segment = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert per_word[1:] == per_segment[1:] == (True, "ok")


def test_a_segment_short_of_the_floor_is_still_refused(monkeypatch):
    """The fix must not turn the word floor off: four words in one entry still fail."""
    monkeypatch.setattr(
        speaker_sample,
        "deepgram_prerecorded_from_bytes",
        lambda *_a, **_k: _make_segments(["thanks for joining today"]),
    )

    transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert (transcript, is_valid) == (None, False)
    assert reason == f"insufficient_words: 4/{speaker_sample.MIN_WORDS}"


def test_the_dominant_ratio_weighs_segments_by_their_words(monkeypatch):
    """Two segments, one long and one short: counting entries would call it a 50/50 split.

    Entry counting gives ratio 0.50 and rejects a sample that is 90% one speaker; word counting
    gives 0.90 and accepts it. The inverse case — one entry per speaker with equal weight — is what
    used to let a genuinely mixed sample through on a single-segment provider.
    """
    segments = _make_segments(
        ["one two three four five six seven eight nine", "interrupting"],
        speakers=["SPEAKER_00", "SPEAKER_01"],
    )

    monkeypatch.setattr(speaker_sample, "deepgram_prerecorded_from_bytes", lambda *_a, **_k: segments)

    _transcript, is_valid, reason = asyncio.run(speaker_sample.verify_and_transcribe_sample(b"audio", 16000))

    assert (is_valid, reason) == (True, "ok")
