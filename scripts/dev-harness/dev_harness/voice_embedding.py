"""Production's speaker-embedding route on this machine's CPU.

In production the backend posts a short clip of one speaker to the diarizer
service (``HOSTED_SPEAKER_EMBEDDING_API_URL`` + ``/v2/embedding``) and gets a
voice vector back. The conversation-level speaker step compares those vectors
to decide that a voice in one recorded unit is the voice heard in another, and
to match a voice against the people the account has named. Without the route
every unit keeps its own speaker numbers, so a long conversation shows a new
"Speaker N" every few seconds.

This launcher serves that one route with production's own handler
(``diarizer.embedding.embedding_endpoint_v2``) and therefore the same pinned
model revision. What is substituted is compute and transport:

* the model runs on CPU (production: a GPU pod);
* the HTTP server is the standard library's, because the model runtime
  (``backend/.venv-eval``) carries no ASGI server and takes none for this;
* requests are served one at a time.

The other diarizer routes (``/v1/embedding`` with its access-gated model, and
``/v1/diarization``) are not served: no production recording path on this
stack calls them.

It needs the model runtime the batch worker uses and a Hugging Face token; the
model is downloaded on first start.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT_ENV = "OMI_HARNESS_VOICE_EMBEDDING_PORT"
WORK_DIR_ENV = "OMI_HARNESS_VOICE_EMBEDDING_WORK_DIR"
THREADS_ENV = "OMI_HARNESS_VOICE_EMBEDDING_THREADS"
ROUTE = "/v2/embedding"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def uploaded_file(content_type: str, body: bytes) -> tuple[str, bytes] | None:
    """The ``file`` part of a multipart form: its filename and bytes."""
    message = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    if not message.is_multipart():
        return None
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "file":
            return part.get_filename() or "audio.wav", part.get_payload(decode=True) or b""
    return None


def build_server(port: int, embed, ready: threading.Event) -> ThreadingHTTPServer:
    """``embed(filename, data)`` returns the vector, or raises with ``status_code`` and ``detail``."""
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _answer(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
            if self.path == "/health":
                self._answer(200 if ready.is_set() else 503, {"status": "healthy" if ready.is_set() else "loading"})
            else:
                self._answer(404, {"detail": "Not Found"})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if self.path.split("?", 1)[0] != ROUTE:
                self.rfile.read(length)
                self._answer(404, {"detail": "Not Found"})
                return
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                self.close_connection = True
                self._answer(413 if length > 0 else 422, {"detail": "upload size"})
                return
            upload = uploaded_file(self.headers.get("Content-Type", ""), self.rfile.read(length))
            if upload is None:
                self._answer(422, {"detail": "multipart field 'file' is required"})
                return
            if not ready.is_set():
                self._answer(503, {"detail": "model loading"})
                return
            try:
                with lock:
                    vector = embed(*upload)
            except Exception as error:
                status = getattr(error, "status_code", None)
                if isinstance(status, int):
                    self._answer(status, {"detail": getattr(error, "detail", "")})
                else:
                    print(f"harness_voice_embedding event=failed error={type(error).__name__}", flush=True)
                    self._answer(500, {"detail": "Internal Server Error"})
                return
            self._answer(200, vector)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # one line per vector would bury the stack's logs; failures are printed above

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> int:
    port = int(os.environ.get(PORT_ENV, "0") or 0)
    if port <= 0:
        raise RuntimeError(f"the voice-embedding service needs {PORT_ENV} (set by the dev harness)")
    if not os.environ.get("HUGGINGFACE_TOKEN", "").strip():
        raise RuntimeError("HUGGINGFACE_TOKEN is not set: add one to backend/.env.local-dev")
    work_dir = os.environ.get(WORK_DIR_ENV, "").strip()
    if work_dir:
        # Production's handler writes each upload under ./_temp for the length of the request.
        os.makedirs(work_dir, exist_ok=True)
        os.chdir(work_dir)

    ready = threading.Event()
    handler: dict[str, object] = {}

    def embed(filename: str, data: bytes):
        from fastapi import UploadFile

        return handler["endpoint"](UploadFile(file=io.BytesIO(data), filename=filename))  # type: ignore[operator]

    def load() -> None:
        import torch

        threads = int(os.environ.get(THREADS_ENV, "0") or 0)
        if threads > 0:
            torch.set_num_threads(threads)
        import diarizer.embedding as production

        production._get_inference(2)  # the /v2 model only; /v1's is access-gated and unused here
        handler["endpoint"] = production.embedding_endpoint_v2
        ready.set()
        print("harness_voice_embedding event=ready device=cpu", flush=True)

    server = build_server(port, embed, ready)
    print(f"harness_voice_embedding event=starting port={port}", flush=True)
    # Listen first: a caller during the model download gets 503 and takes production's
    # "embedding unavailable" path instead of a refused connection.
    threading.Thread(target=server.serve_forever, daemon=True).start()
    load()
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
