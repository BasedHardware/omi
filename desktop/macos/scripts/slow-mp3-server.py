#!/usr/bin/env python3
"""Local-only slow-drip MP3 server for the desktop progressive TTS harness."""

from __future__ import annotations

import argparse
import http.server
import pathlib
import time


class SlowMP3Handler(http.server.BaseHTTPRequestHandler):
    server_version = "OmiSlowMP3/1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        if self.path != "/sample.mp3":
            self.send_error(404)
            return
        payload = self.server.mp3_path.read_bytes()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            for offset in range(0, len(payload), self.server.chunk_size):  # type: ignore[attr-defined]
                self.wfile.write(payload[offset : offset + self.server.chunk_size])  # type: ignore[attr-defined]
                self.wfile.flush()
                time.sleep(self.server.delay_seconds)  # type: ignore[attr-defined]
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mp3", type=pathlib.Path)
    parser.add_argument("port_file", type=pathlib.Path)
    parser.add_argument("--chunk-size", type=int, default=4096)
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowMP3Handler)
    server.mp3_path = args.mp3  # type: ignore[attr-defined]
    server.chunk_size = args.chunk_size  # type: ignore[attr-defined]
    server.delay_seconds = args.delay  # type: ignore[attr-defined]
    args.port_file.write_text(str(server.server_port), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
