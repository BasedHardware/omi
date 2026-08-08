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

const READY_TIMEOUT_MS = 20_000;

export interface LiveServer {
  readonly baseUrl: string;
  stop(): Promise<void>;
}

export async function startLiveServer(): Promise<LiveServer> {
  const port = await freePort();
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

async function freePort(): Promise<number> {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("") });
  const port = probe.port;
  await probe.stop(true);
  return port;
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
  } = {},
): Promise<{ status: number; text: string }> {
  const name = options.name ?? "read_synthesized_memory";
  const args: Record<string, unknown> = { limit: options.limit ?? 3 };
  if (options.cursor != null) {
    args.cursor = options.cursor;
  }
  const response = await fetch(`${baseUrl}/mcp`, {
    method: "POST",
    headers: {
      accept: "application/json, text/event-stream",
      authorization: options.key ?? QA_KEY,
      "content-type": "application/json",
      "mcp-method": "tools/call",
      "mcp-name": name,
      "mcp-protocol-version": PROTOCOL_VERSION,
    },
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
