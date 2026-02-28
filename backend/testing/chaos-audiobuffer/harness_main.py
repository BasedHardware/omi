"""
Chaos engineering harness — FastAPI wrapper for pusher.py with buffer introspection.

Usage:
    PUSHER_MODULE=pusher_vuln uvicorn harness_main:app --host 0.0.0.0 --port 18090
    PUSHER_MODULE=pusher_fixed uvicorn harness_main:app --host 0.0.0.0 --port 18091
"""

import importlib
import os
import sys

from fastapi import FastAPI

# Add mock_deps to Python path so pusher.py's imports resolve to our mocks
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mock_deps"))

# Import the pusher module specified by environment variable
pusher_module_name = os.environ.get("PUSHER_MODULE", "pusher_vuln")
pusher = importlib.import_module(pusher_module_name)

app = FastAPI()
app.include_router(pusher.router)

# Create temp dirs the original main.py creates
for path in ["_temp", "_samples", "_segments", "_speech_profiles"]:
    os.makedirs(path, exist_ok=True)


@app.get("/health")
def health_check():
    return {"status": "healthy", "module": pusher_module_name}


@app.get("/debug/buffers")
def debug_buffers():
    metrics = getattr(pusher, "debug_metrics", {})
    # Ensure keys exist for consistent payloads
    return {
        "module": pusher_module_name,
        "audiobuffer_len": metrics.get("audiobuffer_len", 0),
        "trigger_audiobuffer_len": metrics.get("trigger_audiobuffer_len", 0),
        "audio_chunks": metrics.get("audio_chunks", 0),
        "last_update_ts": metrics.get("last_update_ts", 0.0),
    }
