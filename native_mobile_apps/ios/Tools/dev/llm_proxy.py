#!/usr/bin/env python3
"""Local OpenAI-compatible proxy that serves the Omi backend's OpenAI calls with Gemini or OpenRouter.

For local development only: the upstream harness needs OpenAI for chat, the agent and conversation
summaries, and this lets a developer run it end to end with a Gemini or OpenRouter key instead. Point
the backend at it with OPENAI_BASE_URL=http://127.0.0.1:9911/v1 (read by the OpenAI SDK, langchain
and the backend's LLM gateway). Streamed requests (chat, agent) go to the chat model, the rest (background
extraction under a 35 s deadline) to a fast model; embeddings keep the requested dimensions.

Usage: OPENROUTER_API_KEY=... llm_proxy.py --provider openrouter
       GEMINI_API_KEY=... llm_proxy.py [--provider gemini] [--port 9911] [--chat-model ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# base URL, key variable, chat model (streamed chat and agent), fast model (background
# extraction: summaries, action items, memories, which the backend cuts off after 35 s), embeddings
PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
               "gemini-2.5-flash-lite", "gemini-2.5-flash-lite", "gemini-embedding-001"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                   "openai/gpt-4.1-nano", "google/gemini-2.5-flash-lite", "openai/text-embedding-3-large"),
}
# Every OpenRouter call stays under $0.20/M input and $0.50/M output, cheapest provider first.
OPENROUTER_PREFERENCES = {"sort": "price", "max_price": {"prompt": 0.20, "completion": 0.50}}
# The backend's web search tool asks its LLM gateway for this lane (Perplexity Sonar in production).
# Served here by the fast model with OpenRouter's web plugin: ~$0.0075 per search (3 results).
WEB_SEARCH_LANE = "omi:auto:web-search"
WEB_SEARCH_RESULTS = 3
# OpenAI-only request fields Gemini's compatibility layer rejects.
DROP_FIELDS = {
    "reasoning_effort", "prompt_cache_retention", "prompt_cache_key", "service_tier", "store", "metadata",
    "parallel_tool_calls", "logprobs", "top_logprobs", "user", "verbosity", "safety_identifier", "modalities",
}


class Handler(BaseHTTPRequestHandler):
    chat_model = "gemini-2.5-flash-lite"
    fast_model = "gemini-2.5-flash-lite"
    embedding_model = "gemini-embedding-001"
    provider = "gemini"
    base_url = PROVIDERS["gemini"][0]
    api_key = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("llm-proxy: " + (fmt % args) + "\n")

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": self.chat_model, "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/chat/completions"):
            requested = body.get("model")
            if requested == WEB_SEARCH_LANE:
                self._web_search(body)
                return
            body["model"] = self.chat_model if body.get("stream") else self.fast_model
            for field in DROP_FIELDS:
                body.pop(field, None)
            if "max_completion_tokens" in body and "max_tokens" not in body:
                body["max_tokens"] = body.pop("max_completion_tokens")
            # Gemini (also behind OpenRouter) has no "developer" role.
            for message in body.get("messages", []):
                if message.get("role") == "developer":
                    message["role"] = "system"
            if self.provider == "openrouter":
                body["provider"] = OPENROUTER_PREFERENCES
                body["reasoning"] = {"enabled": False}
            self.log_message("chat %s -> %s stream=%s", requested, body["model"], bool(body.get("stream")))
            self._forward("/chat/completions", body)
        elif self.path.endswith("/embeddings"):
            body["model"] = self.embedding_model
            self._forward("/embeddings", body)
        else:
            self._json(404, {"error": {"message": f"unsupported path {self.path}"}})

    def _web_search(self, body: dict):
        """Answers the web search lane in the shape the backend's Perplexity tool reads:
        choices[0].message.content plus `citations` ({url, title})."""
        if self.provider != "openrouter":
            self._json(503, {"error": {"message": "web search needs --provider openrouter"}})
            return
        body = {
            "model": self.fast_model,
            "messages": body.get("messages", []),
            "max_tokens": body.get("max_tokens", 1000),
            "temperature": body.get("temperature", 0.2),
            "plugins": [{"id": "web", "max_results": WEB_SEARCH_RESULTS}],
            "provider": OPENROUTER_PREFERENCES,
        }
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as upstream:
                result = json.load(upstream)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.log_message("web search upstream %s: %s", error.code, payload[:300])
            self._json(error.code, {"error": {"message": payload.decode(errors="replace")[:300]}})
            return
        message = result.get("choices", [{}])[0].get("message", {})
        result["citations"] = [
            {"url": note["url_citation"].get("url", ""), "title": note["url_citation"].get("title", "")}
            for note in message.get("annotations") or [] if note.get("type") == "url_citation"
        ]
        self.log_message("web search: %d sources, cost %s", len(result["citations"]), result.get("usage", {}).get("cost"))
        self._json(200, result)

    def _forward(self, path: str, body: dict):
        request = urllib.request.Request(
            self.base_url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            upstream = urllib.request.urlopen(request, timeout=180)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.log_message("upstream %s: %s", error.code, payload[:300])
            self.send_response(error.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(200)
        self.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
        self.end_headers()
        while chunk := upstream.read1(8192) if hasattr(upstream, "read1") else upstream.read(8192):
            self.wfile.write(chunk)
            self.wfile.flush()

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GatewayHandler(Handler):
    """Sits in front of the harness's LLM gateway: answers the web search lane (which the local
    gateway has no route for) and passes every other request through unchanged."""

    upstream = "http://127.0.0.1:9080"

    def do_GET(self):
        self._pass_through(b"")

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith("/chat/completions"):
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            if body.get("model") == WEB_SEARCH_LANE:
                self._web_search(body)
                return
        self._pass_through(raw)

    def _pass_through(self, raw: bytes):
        skip = {"host", "content-length", "connection", "accept-encoding"}
        request = urllib.request.Request(
            self.upstream + self.path, data=raw or None, method=self.command,
            headers={k: v for k, v in self.headers.items() if k.lower() not in skip},
        )
        try:
            upstream = urllib.request.urlopen(request, timeout=300)
            status = upstream.status
        except urllib.error.HTTPError as error:
            upstream, status = error, error.code
        self.send_response(status)
        for key, value in upstream.headers.items():
            if key.lower() not in {"transfer-encoding", "connection", "content-length"}:
                self.send_header(key, value)
        self.end_headers()
        while chunk := upstream.read1(8192) if hasattr(upstream, "read1") else upstream.read(8192):
            self.wfile.write(chunk)
            self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9911)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="gemini")
    parser.add_argument("--chat-model")
    parser.add_argument("--fast-model")
    parser.add_argument("--gateway-port", type=int, help="also front the harness LLM gateway on this port")
    parser.add_argument("--gateway-upstream", default="http://127.0.0.1:9080")
    args = parser.parse_args()
    base_url, key_variable, chat_model, fast_model, embedding_model = PROVIDERS[args.provider]
    key = os.environ.get(key_variable, "")
    if not key:
        print(f"{key_variable} is required", file=sys.stderr)
        return 2
    Handler.api_key = key
    Handler.base_url = base_url
    Handler.provider = args.provider
    Handler.chat_model = args.chat_model or chat_model
    Handler.fast_model = args.fast_model or fast_model
    Handler.embedding_model = embedding_model
    print(f"llm-proxy on http://127.0.0.1:{args.port}/v1 -> {args.provider} "
          f"chat {Handler.chat_model}, background {Handler.fast_model}", flush=True)
    if args.gateway_port:
        GatewayHandler.upstream = args.gateway_upstream.rstrip("/")
        gateway = ThreadingHTTPServer(("127.0.0.1", args.gateway_port), GatewayHandler)
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        print(f"llm-proxy gateway front on http://127.0.0.1:{args.gateway_port} -> {GatewayHandler.upstream} "
              f"(web search via {args.provider})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
