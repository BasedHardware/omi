import type { McpHttpRequest, McpHttpResponse } from "./protocol";

/**
 * Hermetic QA-only Bun adapter for the injected MCP protocol handler.
 *
 * Bun's Fetch `Headers` coalesces repeated field lines and exposes no raw
 * header accessor. For headers whose grammar is single-valued at this seam,
 * a comma-joined value is therefore represented as a duplicate so the
 * protocol rejects it. This conservative rule is not a production raw-header
 * multiplicity guarantee.
 */

export const MCP_QA_MAX_REQUEST_BODY_BYTES = 64 * 1024;

export interface McpProtocolHttpHandler {
  handleHttp(request: McpHttpRequest): Promise<McpHttpResponse>;
}

export type BunMcpFetchHandler = (request: Request) => Promise<Response>;

const FAIL_CLOSED_SINGLE_VALUE_HEADERS = new Set([
  "authorization",
  "content-type",
  "mcp-method",
  "mcp-name",
  "mcp-protocol-version",
  "origin",
]);

export function createBunMcpHttpHandler(protocol: McpProtocolHttpHandler): BunMcpFetchHandler {
  return async (request: Request): Promise<Response> => {
    const body = request.method === "POST"
      ? await readBoundedJsonBody(request)
      : undefined;
    const response = await protocol.handleHttp({
      method: request.method,
      headers: translateHeaders(request.headers),
      body,
    });

    return toBunResponse(response);
  };
}

function translateHeaders(headers: Headers): Record<string, string | undefined> {
  const translated: Record<string, string | undefined> = Object.create(null);

  for (const [rawName, value] of headers.entries()) {
    const name = rawName.toLowerCase();
    translated[name] = value;

    // Bun joins repeated request fields with a comma before Fetch exposes
    // them. Single-valued security/dispatch headers cannot safely recover
    // their original field-line boundaries, so retain ambiguity as a
    // case-insensitive duplicate for protocol.ts to reject fail-closed.
    if (FAIL_CLOSED_SINGLE_VALUE_HEADERS.has(name) && value.includes(",")) {
      translated[alternateHeaderCase(name)] = value;
    }
  }

  return translated;
}

function alternateHeaderCase(name: string): string {
  return `${name[0]?.toUpperCase() ?? "X"}${name.slice(1)}`;
}

async function readBoundedJsonBody(request: Request): Promise<unknown> {
  if (request.body === null) {
    return undefined;
  }

  const declaredLength = request.headers.get("content-length");
  if (declaredLength !== null && /^[0-9]+$/.test(declaredLength)) {
    const bytes = Number(declaredLength);
    if (!Number.isSafeInteger(bytes) || bytes > MCP_QA_MAX_REQUEST_BODY_BYTES) {
      await cancelBody(request.body);
      return undefined;
    }
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let byteLength = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      if (!(value instanceof Uint8Array)
        || value.byteLength > MCP_QA_MAX_REQUEST_BODY_BYTES - byteLength) {
        await cancelReader(reader);
        return undefined;
      }
      chunks.push(value);
      byteLength += value.byteLength;
    }
  } catch {
    await cancelReader(reader);
    return undefined;
  } finally {
    reader.releaseLock();
  }

  const bytes = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    const json = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return JSON.parse(json) as unknown;
  } catch {
    return undefined;
  }
}

async function cancelBody(body: ReadableStream<Uint8Array>): Promise<void> {
  try {
    await body.cancel();
  } catch {
    // A failed cancellation still yields no parsed input to the protocol.
  }
}

async function cancelReader(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<void> {
  try {
    await reader.cancel();
  } catch {
    // A failed cancellation still yields no parsed input to the protocol.
  }
}

function toBunResponse(response: McpHttpResponse): Response {
  return new Response(
    response.body === undefined ? null : JSON.stringify(response.body),
    { status: response.status, headers: response.headers },
  );
}
