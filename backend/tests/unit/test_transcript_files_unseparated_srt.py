"""Cues in an SRT block without blank line separators.

Numbered SRT cues that lack blank-line separators previously collapsed into the
first cue, with subsequent sequence numbers and raw timings included in its text.
Ensure each timing line starts a distinct cue and preceding sequence numbers are omitted.
"""

import pytest
from utils.imports import transcript_files as tf


@pytest.mark.parametrize('extension', ['.srt', '.txt'])
def test_numbered_cues_without_blank_lines_each_become_a_cue(extension):
    """A block of several numbered cues collapsed into the first cue, timings and numbers in its text."""
    text = (
        '1\n00:00:01,000 --> 00:00:02,000\nAlice: Hello\nthere\n'
        '2\n00:00:03,000 --> 00:00:04,000\nBob: World\n'
        '3\n00:00:05,000 --> 00:00:06,000\nAlice: Again\n'
    )

    parsed = tf.parse_transcript_file(f'call{extension}', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.speaker, cue.text, cue.start, cue.end) for cue in parsed.cues] == [
        ('Alice', 'Hello there', 1.0, 2.0),
        ('Bob', 'World', 3.0, 4.0),
        ('Alice', 'Again', 5.0, 6.0),
    ]


def test_a_cue_whose_text_is_a_number_keeps_it():
    text = '1\n00:00:01,000 --> 00:00:02,000\n42\n\n2\n00:00:03,000 --> 00:00:04,000\nok\n'

    parsed = tf.parse_transcript_file('call.srt', text.encode('utf-8'))

    assert parsed is not None
    assert [(cue.text, cue.start) for cue in parsed.cues] == [('42', 1.0), ('ok', 3.0)]
