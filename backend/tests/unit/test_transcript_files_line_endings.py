"""Line-ending normalization for transcript imports.

A Windows tool re-saving a CRLF file in text mode emits \r\r\n — one
carriage return too many. Normalization must collapse every carriage-return
variant to a single line feed so SRT and plain-text imports parse the same
as their LF, CR and CRLF counterparts.
"""

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


def test_normalize_collapses_all_line_endings():
    for eol in ('\n', '\r', '\r\n', '\r\r\n', '\r\r\r\n'):
        assert tf._normalize('a{}b'.format(eol)) == 'a\nb', eol


def test_normalize_preserves_blank_lines():
    for eol in ('\n', '\r', '\r\n', '\r\r\n'):
        assert tf._normalize('a{eol}{eol}b'.format(eol=eol)) == 'a\n\nb', eol


def test_srt_import_parses_every_line_ending():
    for eol in ('\n', '\r', '\r\n', '\r\r\n'):
        parsed = tf.parse_transcript_file(
            'd.srt', (eol.join(SRT_LINES) + eol).encode())
        assert parsed is not None, eol
        assert _cues(parsed) == EXPECTED_CUES, eol


def test_txt_import_parses_crcrlf():
    parsed = tf.parse_transcript_file('d.txt', 'Alice: Hi\r\r\nBob: Yo\r\r\n'.encode())
    assert parsed is not None
