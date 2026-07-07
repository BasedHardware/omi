from pathlib import Path


def test_speaker_id_queue_payload_excludes_transcript_text():
    source = Path(__file__).resolve().parents[2] / 'routers' / 'transcribe.py'
    text = source.read_text(encoding='utf-8')
    assert "'text': segment.text" not in text
    assert '"text": segment.text' not in text
    assert 'speaker_id_segment_queue.put_nowait' in text
