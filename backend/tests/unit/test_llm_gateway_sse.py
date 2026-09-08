import pytest

from llm_gateway.gateway import sse as sse_module
from llm_gateway.gateway.sse import MAX_SSE_FRAME_BUFFER_BYTES, SSEEventDecoder


def test_sse_decoder_handles_fragmented_crlf_frames():
    decoder = SSEEventDecoder()

    assert decoder.feed(b'event: message_st') == []
    assert decoder.feed(b'op\r') == []
    events = decoder.feed(b'\ndata: {"type": "message_stop"}\r\n\r\n')

    assert len(events) == 1
    assert events[0].event == 'message_stop'
    assert events[0].data == '{"type": "message_stop"}'


def test_sse_decoder_does_not_treat_terminal_text_inside_payload_as_event_boundary():
    decoder = SSEEventDecoder()

    events = decoder.feed(
        b'event: content_block_delta\n'
        b'data: {"type":"content_block_delta","text":"event: message_stop and data: [DONE]"}\n\n'
    )

    assert len(events) == 1
    assert events[0].event == 'content_block_delta'
    assert events[0].data != '[DONE]'


def test_sse_decoder_accepts_large_chunk_of_individually_bounded_frames(monkeypatch):
    decoder = SSEEventDecoder()
    frame = b'event: ping\ndata: {}\n\n'
    frame_count = 5
    monkeypatch.setattr(sse_module, 'MAX_SSE_FRAME_BUFFER_BYTES', len(frame) * (frame_count - 1))

    events = decoder.feed(frame * frame_count)

    assert len(events) == frame_count
    assert events[0].event == 'ping'


def test_sse_decoder_rejects_one_oversized_incomplete_frame():
    decoder = SSEEventDecoder()

    with pytest.raises(ValueError, match='SSE frame exceeds'):
        decoder.feed(b'data: ' + (b'x' * MAX_SSE_FRAME_BUFFER_BYTES))
