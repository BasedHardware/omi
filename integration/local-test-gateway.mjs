#!/usr/bin/env bun
/**
 * Loopback fake LLM gateway for headed polish-manual.
 *
 * POL-001 / AGT-001: this is a local test gateway, never a production model,
 * never api.omi.me, and never a scripted ChatGenerationSource inside
 * apps/service/bin/dev-server.ts. The service still uses
 * createGatewayChatGenerationSource against this loopback.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const DISCLOSURE = "local test gateway";
const DEFAULT_PORT = 8788;
const DEFAULT_TOKEN = "local-test-gateway-token";

const port = Number(process.env.OMI_LOCAL_TEST_GATEWAY_PORT || DEFAULT_PORT);
const token = process.env.OMI_LOCAL_TEST_GATEWAY_TOKEN
  || process.env.OMI_LLM_GATEWAY_SERVICE_TOKEN
  || DEFAULT_TOKEN;
const readyPath = process.env.OMI_LOCAL_TEST_GATEWAY_READY || "";

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  console.error("ERROR: OMI_LOCAL_TEST_GATEWAY_PORT must be an integer 0..65535");
  process.exit(2);
}
if (typeof token !== "string" || token.length < 8) {
  console.error("ERROR: local test gateway token is missing or too short");
  process.exit(2);
}

const sse = [
  `data: ${JSON.stringify({ choices: [{ delta: { content: "Local test gateway " } }] })}\n\n`,
  `data: ${JSON.stringify({
    choices: [{ delta: { content: "answered." } }],
    usage: { prompt_tokens: 8, completion_tokens: 2, total_tokens: 10 },
  })}\n\n`,
  "data: [DONE]\n\n",
].join("");

const server = Bun.serve({
  hostname: "127.0.0.1",
  port,
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && (url.pathname === "/ready" || url.pathname === "/")) {
      return Response.json({
        schema: "omi.local-test-gateway.v1",
        disclosure: DISCLOSURE,
        production_model: false,
      });
    }
    if (request.method !== "POST" || url.pathname !== "/v1/chat/completions") {
      return new Response("not found", { status: 404 });
    }
    const authorization = request.headers.get("authorization") || "";
    if (authorization !== `Bearer ${token}`) {
      return new Response("unauthorized", { status: 401 });
    }
    return new Response(sse, {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    });
  },
});

const url = `http://127.0.0.1:${server.port}`;
const ready = {
  schema: "omi.local-test-gateway.v1",
  disclosure: DISCLOSURE,
  url,
  production_model: false,
  production_host: false,
};
if (readyPath) {
  mkdirSync(dirname(readyPath), { recursive: true });
  writeFileSync(readyPath, `${JSON.stringify(ready, null, 2)}\n`, { mode: 0o600 });
}
console.log(`${DISCLOSURE} listening at ${url} (never a production model, never the production API host)`);
