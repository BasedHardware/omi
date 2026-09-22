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
from __future__ import annotations

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
    args = ap.parse_args()

    DEFAULT_DEVICE, DEFAULT_MODEL = args.device, args.model

    # Warm the model so the first /route isn't slow.
    get_agent(model=args.model, device=args.device)

    import uvicorn  # lazy

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
