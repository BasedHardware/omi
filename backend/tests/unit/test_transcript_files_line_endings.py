"""Line-ending normalization for transcript imports.

A Windows tool re-saving a CRLF file in text mode emits \r\r\n — one
carriage return too many. Normalization must collapse every carriage-return
variant to a single line feed so SRT and plain-text imports parse the same
as their LF, CR and CRLF counterparts.
"""

import pytest
from utils.imports import transcript_files as tf

SRT_LINES = [
    '1',
    '00:00:01,000 --> 00:00:02,000',
    'Alice: Hello',
    '',
    '2',
    '00:00:03,000 --> 00:00:04,000',
    'Bob: World',
]

EXPECTED_CUES = [('Alice', 'Hello', 1.0, 2.0), ('Bob', 'World', 3.0, 4.0)]


def _cues(parsed):
    return [(c.speaker, c.text, c.start, c.end) for c in parsed.cues]


@pytest.mark.parametrize('eol', ['\n', '\r', '\r\n', '\r\r\n', '\r\r\r\n'])
def test_normalize_collapses_all_line_endings(eol):
    assert tf._normalize(f'a{eol}b') == 'a\nb'


@pytest.mark.parametrize('eol', ['\n', '\r', '\r\n', '\r\r\n'])
def test_normalize_preserves_blank_lines(eol):
    assert tf._normalize(f'a{eol}{eol}b') == 'a\n\nb'


@pytest.mark.parametrize('eol', ['\n', '\r', '\r\n', '\r\r\n'])
def test_srt_import_parses_every_line_ending(eol):
    parsed = tf.parse_transcript_file('d.srt', (eol.join(SRT_LINES) + eol).encode('utf-8'))
    assert parsed is not None
    assert _cues(parsed) == EXPECTED_CUES


def test_txt_import_parses_crcrlf():
    parsed = tf.parse_transcript_file('d.txt', 'Alice: Hi\r\r\nBob: Yo\r\r\n'.encode('utf-8'))
    assert parsed is not None
    assert [c.speaker for c in parsed.cues] == ['Alice', 'Bob']
