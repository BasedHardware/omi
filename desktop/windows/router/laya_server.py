#!/usr/bin/env python3
"""Laya "local brain" router — a small sidecar service for Omi's "Ask Omi Anything".

This is a System-1 *decision* router, NOT an LLM: it classifies a request in one
forward pass (intent / needs_tools / difficulty) and returns a routing decision.
A downstream Omi component (the desktop app) uses that decision to pick where to
actually answer — local tool loop, a small local LLM, or cloud — so cheap/local
turns don't burn cloud quota.

Design notes / honest limits:
- Laya's BASE checkpoints are near-chance zero-shot on typed decisions (see the
  laya README "Honest limits"). The intent taxonomy below is Omi-specific, so for
  real accuracy you FINE-TUNE on labelled Omi requests. Until then this still
  works as a conservative router (unknown -> cloud), which is the safe default.
- Laya is TEXT classification. Speaker identification is a separate concern and is
  handled by the local voiceprint/diarization already in the app — NOT here.
- torch / laya / fastapi are imported lazily so this module imports (and the pure
  `decide_route` can be unit-tested) on machines without them installed.

Run:
    pip install -r requirements.txt
    python laya_server.py                 # http://127.0.0.1:8765/route
    python laya_server.py --device cpu --model ./models/laya --port 8765
"""
# NOTE: this module intentionally does NOT use `from __future__ import annotations`.
# PEP 563 stringifies annotations, and FastAPI then fails to resolve the Pydantic
# model `Req` defined locally inside create_app(), silently treating `body: Req` as a
# query parameter -> every valid JSON POST to /route 422s with `{"loc":["query","body"]}`.

import argparse
import os
from typing import Any, Dict

# --- Static config (no heavy imports at module load) ------------------------

DEFAULT_PORT = 8765
DEFAULT_DEVICE = os.environ.get("LAYA_DEVICE", "cpu")  # "cpu", "cuda", "mps"
DEFAULT_MODEL = os.environ.get("LAYA_MODEL", "./models/laya")

# The Omi intent taxonomy. criteria=None lets Laya infer from the key name; the
# instructions make the categories explicit so the decision head is well-posed.
QUESTIONS: Dict[str, Dict[str, Any]] = {
    "intent": {
        "type": "choice",
        "instructions": "Classify the user's request.",
        "criteria": {
            "memory_search": None,
            "screen_search": None,
            "task_command": None,
            "general_answer": None,
            "sensitive": None,
        },
    },
    "needs_tools": {
        "type": "choice",
        "instructions": "Does this request require accessing Omi data or tools?",
        "criteria": {"yes": None, "no": None},
    },
    "difficulty": {
        "type": "score",
        "instructions": "How difficult is this request?",
        "criteria": {"min": 0, "max": 1},
    },
}

EASY_THRESHOLD = float(os.environ.get("LAYA_EASY_THRESHOLD", "0.3"))


def decide_route(result: Dict[str, Any]) -> Dict[str, Any]:
    """Pure routing from a Laya predict() result -> an Omi route decision.

    Importable + testable with no torch/laya: pass any dict shaped like Laya's
    {"answers": {...}} output. Unknown/absent intent fails safe to cloud.
    """
    answers = (result or {}).get("answers", {}) or {}
    intent = (answers.get("intent") or {}).get("choice")
    needs_tools = ((answers.get("needs_tools") or {}).get("choice") == "yes")
    difficulty = (answers.get("difficulty") or {}).get("score")
    try:
        difficulty = float(difficulty) if difficulty is not None else None
    except (TypeError, ValueError):
        difficulty = None

    if intent == "sensitive":
        route = "confirm_or_refuse"
    elif intent == "memory_search":
        route = "omi_local_memory"
    elif intent == "screen_search":
        route = "omi_local_screen_history"
    elif intent == "task_command":
        route = "omi_task_tools"
    elif difficulty is not None and difficulty < EASY_THRESHOLD and not needs_tools:
        route = "small_local_llm"
    else:
        # general_answer, anything hard/unknown -> cloud (the current safe default)
        route = "large_local_llm_or_cloud"

    return {
        "route": route,
        "intent": intent,
        "needs_tools": needs_tools,
        "difficulty": difficulty,
    }


# --- Model (lazy) + HTTP server (lazy) --------------------------------------

_agent = None


def get_agent(model: str = DEFAULT_MODEL, device: str = DEFAULT_DEVICE):
    """Lazily build the Laya agent once (loads torch/laya only when needed)."""
    global _agent
    if _agent is None:
        from laya.agent import Agent  # lazy: requires torch/laya at runtime only

        _agent = Agent(model_id_or_path=model, device=device)
    return _agent


def predict_route(text: str, model: str = DEFAULT_MODEL, device: str = DEFAULT_DEVICE) -> Dict[str, Any]:
    result = get_agent(model=model, device=device).predict({"request": text}, QUESTIONS)
    return decide_route(result)


# --- Mock mode: run the HTTP + routing contract with ZERO deps (no torch/laya).
# A small keyword heuristic stands in for the Laya decision head so the sidecar
# contract and the app's "Local brain" wiring can be exercised end-to-end today.
import re as _re  # noqa: E402  (mock-only)

_MOCK_RULES = [
    ("sensitive", ("password", "secret", "delete", "transfer money", "wire", "otp", "credit card", "private key")),
    ("screen_search", ("screen", "screenshot", "what am i looking at", "on my screen", "window")),
    ("task_command", ("remind", "reminder", "add task", "create task", "schedule", "email", "send message", "text ", "call ")),
    ("memory_search", ("remember", "i said", "we discussed", "last time", "my notes", "what did i", "did i")),
]


def mock_decide(text: str) -> Dict[str, Any]:
    low = f" {text.lower()} "
    intent = "general_answer"
    for name, needles in _MOCK_RULES:
        if any(n in low for n in needles):
            intent = name
            break
    needs_tools = intent in ("memory_search", "screen_search", "task_command")
    # fake difficulty: short/simple -> easy, long/complex -> hard
    words = len(text.split())
    difficulty = 0.2 if words <= 6 else 0.7
    return decide_route(
        {
            "answers": {
                "intent": {"choice": intent},
                "needs_tools": {"choice": "yes" if needs_tools else "no"},
                "difficulty": {"score": difficulty},
            }
        }
    )


def run_mock_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    import json as _json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: Dict[str, Any]) -> None:
            body = _json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                self._send(200, {"ok": True, "mode": "mock"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/route":
                self._send(404, {"error": "not found"})
                return
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                payload = _json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                self._send(400, {"error": "bad json"})
                return
            self._send(200, mock_decide(str(payload.get("request", ""))))

        def log_message(self, *_a):  # keep it quiet
            return

    srv = HTTPServer((host, port), Handler)
    print(f"[laya-router] MOCK mode (no torch/laya) on http://{host}:{port}  "
          f"(POST /route {{'request': text}}, GET /health). Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


def create_app():
    from fastapi import FastAPI  # lazy
    from pydantic import BaseModel  # lazy

    app = FastAPI(title="omi-laya-router")

    class Req(BaseModel):
        request: str

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "device": DEFAULT_DEVICE, "model": DEFAULT_MODEL}

    @app.post("/route")
    def route(body: Req) -> Dict[str, Any]:
        return predict_route(body.request)

    return app


def main() -> None:
    global DEFAULT_DEVICE, DEFAULT_MODEL
    ap = argparse.ArgumentParser(description="Omi Laya local-brain router")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=DEFAULT_DEVICE, choices=["cpu", "cuda", "mps"])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--mock", action="store_true",
                    help="run the HTTP + routing contract with a keyword stub; no torch/laya needed")
    args = ap.parse_args()

    DEFAULT_DEVICE, DEFAULT_MODEL = args.device, args.model

    if args.mock:
        run_mock_server(args.host, args.port)
        return

    try:
        import uvicorn  # lazy

        get_agent(model=args.model, device=args.device)  # warm the model
    except ImportError as e:
        raise SystemExit(
            f"\n[laya-router] real mode needs `{e.name}` (and torch + a laya checkpoint).\n"
            f"  Install deps:  uv venv && uv pip install -r requirements.txt\n"
            f"  Or test now with no install:  python3 laya_server.py --mock\n"
        )

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
