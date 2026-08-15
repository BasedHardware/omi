#!/usr/bin/env bun
/**
 * Loopback lane-to-model gateway shim.
 *
 * Opt-in only: integration/dev-stack.sh launches this instead of the canned
 * local test gateway when OMI_CHAT_MODEL=real. It is a real-model proxy
 * (GLM / Z.ai by default). Chat's UI label follows the `/ready` self-description
 * (`real_model_proxy` plus the model id) through the service capability receipt.
 * Attachments still fail closed in the service generation source.
 *
 * Enable:
 *   GLM_API_KEY=... OMI_CHAT_MODEL=real integration/dev-stack.sh --up
 * Key env names (first non-empty wins): GLM_API_KEY, ZAI_API_KEY,
 * OMI_BENCH_OPENAI_API_KEY. Optional: OMI_BENCH_OPENAI_BASE_URL,
 * OMI_BENCH_OPENAI_MODEL, OMI_LOCAL_MODEL_GATEWAY_TOKEN,
 * OMI_LOCAL_MODEL_GATEWAY_PORT (default 8791).
 */
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

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
const logDir = join((process.env.OMI_DEV_STACK_RUNDIR || "/tmp/omi-dev-stack").trim() || "/tmp/omi-dev-stack", "logs");

const gatewayLog = (level, event, fields = {}) => {
  try {
    mkdirSync(logDir, { recursive: true });
    appendFileSync(join(logDir, "gateway.jsonl"), `${JSON.stringify({
      ts: new Date().toISOString(),
      proc: "gateway",
      level,
      event,
      ...fields,
    })}\n`, "utf8");
  } catch {
    // Observability must never change the proxied generation.
  }
};

const sseDataPayloads = (event) => event
  .split(/\r?\n/)
  .filter((line) => line.startsWith("data:"))
  .map((line) => line.slice(5).trimStart());

const observeUpstreamSse = (body, startedAt) => {
  if (body === null) return { stream: null, done: Promise.resolve(null) };
  let byteCount = 0;
  let frameCount = 0;
  let buffer = "";
  let sawDone = false;
  let firstContentMs = null;
  let firstReasoningMs = null;
  let finishReason = null;
  const decoder = new TextDecoder();
  const note = (record) => {
    const choices = Array.isArray(record.choices) ? record.choices[0] : null;
    if (choices === null || typeof choices !== "object") return;
    const elapsed = Date.now() - startedAt;
    if (typeof choices.finish_reason === "string" && /^[a-z_]{1,32}$/u.test(choices.finish_reason)) {
      finishReason = choices.finish_reason;
    }
    const delta = choices.delta;
    if (delta === null || typeof delta !== "object") return;
    const reasoning = typeof delta.reasoning_content === "string" && delta.reasoning_content.length > 0
      ? delta.reasoning_content
      : (typeof delta.reasoning === "string" && delta.reasoning.length > 0 ? delta.reasoning : null);
    if (reasoning !== null && firstReasoningMs === null) firstReasoningMs = elapsed;
    if (typeof delta.content === "string" && delta.content.length > 0 && firstContentMs === null) {
      firstContentMs = elapsed;
    }
  };
  const dispatch = (event) => {
    const data = sseDataPayloads(event).join("\n");
    if (data.length === 0) return;
    frameCount += 1;
    if (data === "[DONE]") {
      sawDone = true;
      return;
    }
    try {
      const parsed = JSON.parse(data);
      if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) note(parsed);
    } catch {
      // Count the frame; never inspect payload text beyond the JSON shape.
    }
  };
  let finished;
  const done = new Promise((resolve) => { finished = resolve; });
  const stream = new ReadableStream({
    async start(controller) {
      const reader = body.getReader();
      try {
        while (true) {
          const next = await reader.read();
          if (next.value !== undefined) {
            byteCount += next.value.byteLength;
            controller.enqueue(next.value);
            buffer += decoder.decode(next.value, { stream: !next.done });
            const events = buffer.split(/\r?\n\r?\n/);
            buffer = events.pop() ?? "";
            for (const event of events) dispatch(event);
          }
          if (next.done) {
            if (buffer.trim().length > 0) dispatch(buffer);
            controller.close();
            break;
          }
        }
      } catch (error) {
        controller.error(error);
      } finally {
        finished({
          byteCount,
          frameCount,
          sawDone,
          firstContentMs,
          firstReasoningMs,
          finishReason,
          reasoningPreambleMs: firstContentMs === null || firstReasoningMs === null
            ? null
            : Math.max(0, firstContentMs - firstReasoningMs),
          durationMs: Date.now() - startedAt,
        });
      }
    },
  });
  return { stream, done };
};

const readinessBody = () => ({
  schema: "omi.local-model-gateway.v1",
  disclosure: DISCLOSURE,
  real_model_proxy: true,
  provider_host: providerHost,
  model: modelId,
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
    const startedAt = Date.now();
    gatewayLog("info", "upstream_request_started", { providerHost, attempt: 1 });
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
      gatewayLog("error", "upstream_error", {
        kind: "unreachable",
        elapsedMs: Date.now() - startedAt,
        providerHost,
      });
      return new Response("provider unreachable", { status: 502 });
    }
    gatewayLog(upstream.ok ? "info" : "warn", "upstream_status", {
      status: upstream.status,
      elapsedMs: Date.now() - startedAt,
      providerHost,
    });
    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    const observed = observeUpstreamSse(upstream.body, startedAt);
    void observed.done.then((stats) => {
      if (stats === null) return;
      gatewayLog("info", "upstream_stream", {
        status: upstream.status,
        ...stats,
      });
    });
    return new Response(observed.stream, { status: upstream.status, headers });
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
