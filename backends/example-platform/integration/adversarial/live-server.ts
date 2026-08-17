/**
 * Boots the real backend as a REAL CHILD PROCESS on a real socket.
 *
 * This is deliberately not an in-process handler call. The two properties
 * these tests exist to prove — byte-identity of hidden vs absent, and
 * absence of raw-data leakage — are properties of the BYTES ON THE WIRE.
 * An in-process assertion compares JavaScript objects and would happily pass
 * while the serializer, the header set, the framing, or the content-length
 * differed. That is precisely the class of bug a green unit suite cannot see.
 */

import { FIXTURE_TIMEZONE } from "../server/fixture-clock";
import { freeLoopbackPort } from "../lib/free-port";

const READY_TIMEOUT_MS = 20_000;

export interface LiveServer {
  readonly baseUrl: string;
  stop(): Promise<void>;
}

export async function startLiveServer(): Promise<LiveServer> {
  const port = await freeLoopbackPort();
  const child = Bun.spawn({
    cmd: ["bun", "run", "integration/server/serve.ts"],
    cwd: new URL("../..", import.meta.url).pathname,
    env: { ...process.env, TZ: FIXTURE_TIMEZONE, OMI_INTEGRATION_PORT: String(port) },
    stdout: "pipe",
    stderr: "pipe",
  });

  const baseUrl = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    // The child exiting is itself an outcome: a wrapper that only polls for
    // HTTP readiness reports success while the child already died.
    if (child.exitCode !== null) {
      const stderr = await new Response(child.stderr).text();
      throw new Error(`backend exited before readiness (status ${child.exitCode}): ${stderr}`);
    }
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return {
          baseUrl,
          async stop() {
            child.kill();
            await child.exited;
          },
        };
      }
    } catch {
      // not up yet
    }
    await Bun.sleep(100);
  }

  child.kill();
  await child.exited;
  throw new Error(`backend did not become ready within ${READY_TIMEOUT_MS}ms`);
}

export const QA_KEY = "omi-integration-qa-key-v1";
export const QA_KEY_NO_SCOPE = "omi-integration-qa-key-noscope";
const PROTOCOL_VERSION = "2026-07-28";

/** Returns the RAW RESPONSE TEXT — never a parsed object. Bytes are the subject. */
export async function callTool(
  baseUrl: string,
  options: {
    readonly key?: string;
    readonly name?: string;
    readonly limit?: number;
    readonly cursor?: string | null;
    readonly id?: string;
    /** Value for `x-omi-client-id`, if any — omit to send no header at all. */
    readonly clientId?: string;
  } = {},
): Promise<{ status: number; text: string }> {
  const name = options.name ?? "read_synthesized_memory";
  const args: Record<string, unknown> = { limit: options.limit ?? 3 };
  if (options.cursor != null) {
    args.cursor = options.cursor;
  }
  const headers: Record<string, string> = {
    accept: "application/json, text/event-stream",
    authorization: options.key ?? QA_KEY,
    "content-type": "application/json",
    "mcp-method": "tools/call",
    "mcp-name": name,
    "mcp-protocol-version": PROTOCOL_VERSION,
  };
  if (options.clientId !== undefined) {
    headers["x-omi-client-id"] = options.clientId;
  }
  const response = await fetch(`${baseUrl}/mcp`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: options.id ?? "1",
      method: "tools/call",
      params: {
        name,
        arguments: args,
        _meta: {
          "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
          "io.modelcontextprotocol/clientCapabilities": {},
        },
      },
    }),
  });
  return { status: response.status, text: await response.text() };
}

/** Extracts the canonical page JSON string the server emitted, or null. */
export function pageTextOf(responseText: string): string | null {
  try {
    const envelope = JSON.parse(responseText) as {
      result?: { content?: readonly { text?: unknown }[] };
    };
    const text = envelope.result?.content?.[0]?.text;
    return typeof text === "string" ? text : null;
  } catch {
    return null;
  }
}

export async function control(baseUrl: string, path: string): Promise<void> {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) {
    throw new Error(`QA control call failed: ${path} -> ${response.status}`);
  }
}

/** Fetches and parses `/qa/stats` as an untyped object — callers narrow the fields they need. */
export async function stats(baseUrl: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${baseUrl}/qa/stats`);
  if (!response.ok) {
    throw new Error(`GET /qa/stats -> ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}

/**
 * `GET /v1/memories` against a live server, with full header control — used
 * to exercise the settled client recall route the same way the recall-route
 * conformance suite does, but with a caller-controlled `x-omi-client-id`.
 */
export async function recall(
  baseUrl: string,
  options: {
    readonly key?: string;
    readonly limit?: number;
    readonly cursor?: string | null;
    readonly clientId?: string;
  } = {},
): Promise<{ status: number; text: string }> {
  // `Bearer ` is not optional on this route. The registered route
  // (`apps/service/routes/memories.ts`) extracts the token with a strict
  // prefix check and answers 401 without it — the retired hand-rolled door
  // accepted a bare key, one of the bounded compatibility differences this
  // adversarial harness keeps visible.
  const headers: Record<string, string> = { authorization: `Bearer ${options.key ?? QA_KEY}` };
  if (options.clientId !== undefined) {
    headers["x-omi-client-id"] = options.clientId;
  }
  const params = new URLSearchParams();
  if (options.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options.cursor != null) {
    params.set("cursor", options.cursor);
  }
  const query = params.toString();
  const response = await fetch(`${baseUrl}/v1/memories${query ? `?${query}` : ""}`, { headers });
  return { status: response.status, text: await response.text() };
}
