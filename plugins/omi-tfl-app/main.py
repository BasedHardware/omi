"""Run from this directory with: uvicorn main:app --port 8080 --workers 1."""

import json
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from transit import TfLClient, execute

app = FastAPI(title="Omi London Transit", version="1.0.0")
client = TfLClient()


@app.get("/")
def root():
    return {"name": "London Transit", "description": "TfL line status, stop search and arrival predictions for Omi."}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
def manifest():
    return json.loads(Path(__file__).with_name("omi-tools.json").read_text())


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Send the tool parameters as a valid JSON object."})


@app.post("/tools/{tool_name}")
def run_tool(tool_name: str, payload: Any = Body(...)):
    return execute(tool_name, payload, client)
