// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { MCP_PROTOCOL_VERSION, SYNTHESIZED_MEMORY_READ_TOOL } from "../mcp/protocol";

/**
 * Minimal MCP 2026-07-28 client for the QA proofs.
 *
 * It builds requests the transport will actually accept — the envelope,
 * dispatch headers, and `_meta` are all validated server-side — so a proof
 * exercises the real protocol rather than a convenient shortcut around it.
 *
 * It deliberately returns the **raw response text** alongside the parsed body:
 * several proofs assert on emitted bytes, and re-serializing a parsed object
 * would destroy exactly the evidence they need.
 */

export interface McpCallOptions {
  readonly url: string;
  readonly token?: string;
  readonly origin?: string;
  readonly method?: string;
  readonly id?: string | number;
  readonly toolName?: string;
  readonly cursor?: string | null;
  readonly limit?: number;
  /** Explicit item granularity; omitted means the server's stated default. */
  // domain-pending(DIV-DOMCORE-008)
  readonly granularity?: "temporal_leaf" | "all_nodes";
  /** Overrides applied last; use to omit or corrupt headers in negative tests. */
  readonly headerOverrides?: Readonly<Record<string, string | undefined>>;
}

export interface McpCallResult {
  readonly status: number;
  readonly headers: Readonly<Record<string, string>>;
  /** Exact bytes as received. Proofs assert on this, not on a re-serialization. */
  readonly rawBody: string;
  readonly body: unknown;
}

export const mcpCall = async (options: McpCallOptions): Promise<McpCallResult> => {
  const method = options.method ?? "tools/call";
  const id = options.id ?? 1;
  const toolName = options.toolName ?? SYNTHESIZED_MEMORY_READ_TOOL;
  const origin = options.origin ?? new URL(options.url).origin;

  const args: Record<string, unknown> = {};
  if (options.cursor !== undefined && options.cursor !== null) args.cursor = options.cursor;
  if (options.limit !== undefined) args.limit = options.limit;
  if (options.granularity !== undefined) args.granularity = options.granularity;

  const params: Record<string, unknown> = method === "tools/call"
    ? {
      name: toolName,
      arguments: args,
      _meta: {
        "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
      },
    }
    : {
      _meta: {
        "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
      },
    };

  const headers: Record<string, string | undefined> = {
    "content-type": "application/json",
    accept: "application/json, text/event-stream",
    origin,
    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
    "mcp-method": method,
    "mcp-name": method === "tools/call" ? toolName : "",
    ...(options.token === undefined ? {} : { authorization: `Bearer ${options.token}` }),
    ...(options.headerOverrides ?? {}),
  };

  const response = await fetch(`${options.url}/mcp`, {
    method: "POST",
    headers: Object.fromEntries(
      Object.entries(headers).filter((entry): entry is [string, string] => entry[1] !== undefined),
    ),
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });

  const rawBody = await response.text();
  let body: unknown;
  try {
    body = JSON.parse(rawBody) as unknown;
  } catch {
    body = undefined;
  }

  return {
    status: response.status,
    headers: Object.fromEntries(response.headers.entries()),
    rawBody,
    body,
  };
};

/** Extracts the ratified page JSON text from a successful tools/call result. */
export const pageTextOf = (result: McpCallResult): string | null => {
  const content = (result.body as {
    result?: { content?: readonly { type?: string; text?: string }[] };
  } | undefined)?.result?.content;
  const first = content?.[0];
  return first?.type === "text" && typeof first.text === "string" ? first.text : null;
};

export const rpcErrorOf = (result: McpCallResult): { code: number; message: string } | null => {
  const error = (result.body as { error?: { code?: number; message?: string } } | undefined)?.error;
  return typeof error?.code === "number" && typeof error.message === "string"
    ? { code: error.code, message: error.message }
    : null;
};
