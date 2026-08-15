#!/usr/bin/env bun
/**
 * Loopback lane-to-model gateway shim.
 *
 * Opt-in only: integration/dev-stack.sh launches this instead of the canned
 * local test gateway when OMI_CHAT_MODEL=real. It is a real-model proxy
 * (GLM / Z.ai by default). It does not change Chat's UI label — that surface
 * still says "Local test gateway" until separate evidence plumbing exists.
 * Attachments still fail closed in the service generation source.
 *
 * Enable:
 *   GLM_API_KEY=... OMI_CHAT_MODEL=real integration/dev-stack.sh --up
 * Key env names (first non-empty wins): GLM_API_KEY, ZAI_API_KEY,
 * OMI_BENCH_OPENAI_API_KEY. Optional: OMI_BENCH_OPENAI_BASE_URL,
 * OMI_BENCH_OPENAI_MODEL, OMI_LOCAL_MODEL_GATEWAY_TOKEN,
 * OMI_LOCAL_MODEL_GATEWAY_PORT (default 8791).
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

const DISCLOSURE = "local real-model proxy";
const DEFAULT_PORT = 8791;
const DEFAULT_BASE = "https://api.z.ai/api/paas/v4";
const DEFAULT_MODEL = "glm-4.7";
const KEY_ENV_NAMES = Object.freeze(["GLM_API_KEY", "ZAI_API_KEY", "OMI_BENCH_OPENAI_API_KEY"]);
const SAFE_GATEWAY_LANE = /^omi:auto:[a-z0-9][a-z0-9-]{0,95}$/;
const MAX_BODY_BYTES = 1_048_576;
const KEY_REFUSAL = `ERROR: local model gateway requires ${KEY_ENV_NAMES.join(", ")}`;

const port = Number(process.env.OMI_LOCAL_MODEL_GATEWAY_PORT || DEFAULT_PORT);
const token = process.env.OMI_LOCAL_MODEL_GATEWAY_TOKEN || "";
const readyPath = process.env.OMI_LOCAL_MODEL_GATEWAY_READY || "";
const modelId = process.env.OMI_BENCH_OPENAI_MODEL || DEFAULT_MODEL;
const rawBase = (process.env.OMI_BENCH_OPENAI_BASE_URL || DEFAULT_BASE).replace(/\/$/u, "");

const readProviderKey = () => {
  for (const name of KEY_ENV_NAMES) {
    const value = process.env[name];
    if (typeof value === "string" && value.length > 0) return value;
  }
  return "";
};

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  console.error("ERROR: OMI_LOCAL_MODEL_GATEWAY_PORT must be an integer 0..65535");
  process.exit(2);
}
if (typeof token !== "string" || token.length < 8) {
  console.error("ERROR: OMI_LOCAL_MODEL_GATEWAY_TOKEN is missing or too short");
  process.exit(2);
}
const apiKey = readProviderKey();
if (apiKey.length === 0) {
  console.error(KEY_REFUSAL);
  process.exit(2);
}

let providerBase;
try {
  providerBase = new URL(rawBase.includes("://") ? rawBase : `https://${rawBase}`);
} catch {
  console.error("ERROR: OMI_BENCH_OPENAI_BASE_URL is not a valid URL");
  process.exit(2);
}
if ((providerBase.protocol !== "http:" && providerBase.protocol !== "https:")
  || providerBase.username.length > 0 || providerBase.password.length > 0
  || providerBase.hostname === "api.omi.me") {
  console.error("ERROR: OMI_BENCH_OPENAI_BASE_URL is not a usable provider origin");
  process.exit(2);
}
const providerHost = providerBase.hostname;
const providerEndpoint = `${providerBase.toString().replace(/\/$/u, "")}/chat/completions`;

const readinessBody = () => ({
  schema: "omi.local-model-gateway.v1",
  disclosure: DISCLOSURE,
  real_model_proxy: true,
  provider_host: providerHost,
});

const server = Bun.serve({
  hostname: "127.0.0.1",
  port,
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && (url.pathname === "/ready" || url.pathname === "/")) {
      return Response.json(readinessBody());
    }
    if (request.method !== "POST" || url.pathname !== "/v1/chat/completions") {
      return new Response("not found", { status: 404 });
    }
    const authorization = request.headers.get("authorization") || "";
    if (authorization !== `Bearer ${token}`) {
      return new Response("unauthorized", { status: 401 });
    }
    const rawBody = await request.arrayBuffer();
    if (rawBody.byteLength > MAX_BODY_BYTES) {
      return new Response("payload too large", { status: 413 });
    }
    let inbound;
    try {
      inbound = JSON.parse(new TextDecoder().decode(rawBody));
    } catch {
      return new Response("invalid json", { status: 400 });
    }
    if (inbound === null || typeof inbound !== "object" || Array.isArray(inbound)) {
      return new Response("invalid json", { status: 400 });
    }
    const lane = inbound.model;
    if (typeof lane !== "string" || !SAFE_GATEWAY_LANE.test(lane)) {
      return new Response("invalid lane", { status: 400 });
    }
    const forward = {
      model: modelId,
      messages: inbound.messages,
      stream: inbound.stream,
      stream_options: inbound.stream_options,
    };
    if (Object.hasOwn(inbound, "tools")) forward.tools = inbound.tools;
    if (Object.hasOwn(inbound, "tool_choice")) forward.tool_choice = inbound.tool_choice;
    let upstream;
    try {
      upstream = await fetch(providerEndpoint, {
        method: "POST",
        headers: {
          authorization: `Bearer ${apiKey}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(forward),
        signal: request.signal,
      });
    } catch {
      return new Response("provider unreachable", { status: 502 });
    }
    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    return new Response(upstream.body, { status: upstream.status, headers });
  },
});

const listenUrl = `http://127.0.0.1:${server.port}`;
const ready = {
  ...readinessBody(),
  url: listenUrl,
  model: modelId,
};
if (readyPath) {
  mkdirSync(dirname(readyPath), { recursive: true });
  writeFileSync(readyPath, `${JSON.stringify(ready, null, 2)}\n`, { mode: 0o600 });
}
console.log(`${DISCLOSURE} listening at ${listenUrl} (real_model_proxy, host ${providerHost})`);
