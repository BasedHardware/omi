from __future__ import annotations

from dataclasses import dataclass

MAX_SSE_FRAME_BUFFER_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: str


class SSEEventDecoder:
    """Incrementally decode complete SSE frames without inspecting payload substrings."""

    def __init__(self) -> None:
        self._buffer: bytes = b''

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        if not chunk:
            return []
        combined = self._buffer + chunk
        trailing_carriage_return = combined.endswith(b'\r')
        normalizable = combined[:-1] if trailing_carriage_return else combined
        self._buffer = normalizable.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        if trailing_carriage_return:
            self._buffer += b'\r'
        events: list[SSEEvent] = []
        while b'\n\n' in self._buffer:
            raw_frame, self._buffer = self._buffer.split(b'\n\n', 1)
            event_name = 'message'
            data_lines: list[str] = []
            for raw_line in raw_frame.split(b'\n'):
                if raw_line.startswith(b'event:'):
                    event_name = raw_line.removeprefix(b'event:').strip().decode('utf-8', errors='replace')
                elif raw_line.startswith(b'data:'):
                    data_lines.append(raw_line.removeprefix(b'data:').lstrip().decode('utf-8', errors='replace'))
            events.append(SSEEvent(event=event_name or 'message', data='\n'.join(data_lines)))
        if len(self._buffer) > MAX_SSE_FRAME_BUFFER_BYTES:
            raise ValueError('SSE frame exceeds bounded decoder buffer')
        return events
