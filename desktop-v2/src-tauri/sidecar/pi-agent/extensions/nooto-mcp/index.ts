/**
 * Pi extension: MCP bridge.
 *
 * Reads a list of MCP servers from:
 *   1. servers.default.json (shipped with this extension, context7 + playwright)
 *   2. ~/.nooto/coding-agent/mcp.json (user override, deep-merged over default)
 *
 * For each enabled server it spawns the process, performs the MCP initialize
 * handshake, calls tools/list, and registers every discovered tool with Pi as
 * `<serverName>__<toolName>`. Per-server failures are isolated. Cleanup runs
 * on `session_shutdown`.
 */

import type { ExtensionAPI, AgentToolResult } from "@mariozechner/pi-coding-agent";
import { Type, type TSchema, type TObject, type TProperties } from "@sinclair/typebox";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Config types
// ---------------------------------------------------------------------------

interface ServerConfig {
  command: string;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

type ServersMap = Record<string, ServerConfig>;

// ---------------------------------------------------------------------------
// Config loading
// ---------------------------------------------------------------------------

function extensionDir(): string {
  return dirname(fileURLToPath(import.meta.url));
}

function loadDefault(): ServersMap {
  const p = resolve(extensionDir(), "servers.default.json");
  return JSON.parse(readFileSync(p, "utf8")) as ServersMap;
}

function loadUserOverride(): ServersMap | null {
  const p = resolve(homedir(), ".nooto", "coding-agent", "mcp.json");
  try {
    return JSON.parse(readFileSync(p, "utf8")) as ServersMap;
  } catch (err) {
    // ENOENT is the common case — user hasn't created the file yet.
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") {
      console.warn(`[nooto-mcp] Failed to parse user config at ${p}:`, err);
    }
    return null;
  }
}

/**
 * Deep-merge user override onto the default config.
 * Users can disable a server (enabled: false), add new servers, or override args.
 */
function mergeConfigs(base: ServersMap, override: ServersMap | null): ServersMap {
  if (!override) return base;
  const result: ServersMap = { ...base };
  for (const [name, cfg] of Object.entries(override)) {
    result[name] = { ...(result[name] ?? {}), ...cfg };
  }
  return result;
}

function loadServers(): ServersMap {
  return mergeConfigs(loadDefault(), loadUserOverride());
}

// ---------------------------------------------------------------------------
// JSON-Schema → TypeBox converter
// ---------------------------------------------------------------------------
//
// Strategy: recursive structural translation covering the common 80%:
//   string, number, boolean, integer → scalar TypeBox primitives
//   object  → Type.Object({...properties})
//   array   → Type.Array(<converted items>)
//   enum    → Type.Union([Type.Literal(v), ...])
//
// Unsupported: $ref, oneOf, anyOf, allOf, not, if/then/else.
// These fall through to Type.Unknown() so the tool is still registered with a
// permissive parameter type — the call works, the LLM just sees a loose schema.

type JsonSchemaNode = Record<string, unknown>;

function convertSchema(schema: JsonSchemaNode, required: boolean): TSchema {
  // Check enum before type — a node may carry both.
  if (Array.isArray(schema["enum"])) {
    const literals = (schema["enum"] as unknown[]).map((v) =>
      Type.Literal(v as string | number | boolean),
    );
    const union = literals.length === 1 ? literals[0] : Type.Union(literals as [TSchema, TSchema, ...TSchema[]]);
    return required ? union : Type.Optional(union);
  }

  const type = schema["type"] as string | undefined;
  const description = schema["description"] as string | undefined;
  const opts = description ? { description } : {};

  let node: TSchema;

  switch (type) {
    case "string":
      node = Type.String(opts);
      break;

    case "number":
    case "integer":
      node = Type.Number(opts);
      break;

    case "boolean":
      node = Type.Boolean(opts);
      break;

    case "array": {
      const items = schema["items"] as JsonSchemaNode | undefined;
      const itemSchema = items ? convertSchema(items, true) : Type.Unknown();
      node = Type.Array(itemSchema, opts);
      break;
    }

    case "object": {
      const props = schema["properties"] as Record<string, JsonSchemaNode> | undefined;
      const reqFields = new Set((schema["required"] as string[] | undefined) ?? []);
      if (!props) {
        node = Type.Record(Type.String(), Type.Unknown(), opts);
        break;
      }
      const converted: TProperties = {};
      for (const [key, val] of Object.entries(props)) {
        converted[key] = convertSchema(val, reqFields.has(key));
      }
      node = Type.Object(converted, opts) as TObject;
      break;
    }

    default:
      node = Type.Unknown(opts);
      break;
  }

  return required ? node : Type.Optional(node);
}

/**
 * Convert an MCP inputSchema (always type:object at top level) to a TypeBox
 * TObject. Throws if the top-level type is not "object" — caller skips the tool.
 */
function mcpSchemaToTypebox(inputSchema: JsonSchemaNode): TObject {
  if (inputSchema["type"] !== "object") {
    throw new Error(`Top-level inputSchema.type is not "object": ${JSON.stringify(inputSchema["type"])}`);
  }

  const props = (inputSchema["properties"] as Record<string, JsonSchemaNode> | undefined) ?? {};
  const reqFields = new Set((inputSchema["required"] as string[] | undefined) ?? []);

  const converted: TProperties = {};
  for (const [key, val] of Object.entries(props)) {
    converted[key] = convertSchema(val, reqFields.has(key));
  }

  return Type.Object(converted);
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TOOL_CALL_TIMEOUT_MS = 60_000;

// ---------------------------------------------------------------------------
// Extension factory
// ---------------------------------------------------------------------------

export default function registerNootoMcp(pi: ExtensionAPI): void {
  const servers = loadServers();
  const clients: Client[] = [];

  void (async () => {
    const entries = Object.entries(servers).filter(([, cfg]) => cfg.enabled !== false);

    const results = await Promise.allSettled(
      entries.map(([serverName, cfg]) => connectServer(pi, clients, serverName, cfg)),
    );

    results.forEach((result, i) => {
      if (result.status === "rejected") {
        const msg = result.reason instanceof Error ? result.reason.message : String(result.reason);
        console.warn(`[nooto-mcp] ${entries[i][0]}: failed to initialize — ${msg}`);
      }
    });
  })();

  pi.on("session_shutdown", async () => {
    for (const client of clients) {
      try {
        await client.close();
      } catch {
        // Best-effort cleanup.
      }
    }
    clients.length = 0;
  });
}

async function connectServer(
  pi: ExtensionAPI,
  clients: Client[],
  serverName: string,
  cfg: ServerConfig,
): Promise<void> {
  const transport = new StdioClientTransport({
    command: cfg.command,
    args: cfg.args ?? [],
    env: cfg.env,
    // Pipe stderr so noisy MCP server logs don't pollute Pi's RPC stdout.
    stderr: "pipe",
  });

  const client = new Client({ name: "nooto-pi-mcp-bridge", version: "0.1.0" });

  await client.connect(transport);
  clients.push(client);

  const { tools } = await client.listTools();
  // Intentionally silent on success — Pi's stderr pipe is forwarded to the
  // chat as red error bubbles, so any console output here surfaces as a
  // false positive in the UI.

  for (const tool of tools) {
    const piName = `${serverName}__${tool.name}`;

    let parameters: TObject;
    try {
      parameters = mcpSchemaToTypebox(tool.inputSchema as JsonSchemaNode);
    } catch (convErr) {
      console.warn(`[nooto-mcp] ${piName}: schema conversion failed (${String(convErr)}), skipping`);
      continue;
    }

    pi.registerTool({
      name: piName,
      label: `${serverName}: ${tool.name}`,
      description: `[${serverName}] ${tool.description ?? tool.name}`,
      parameters,

      async execute(_toolCallId, params, signal, _onUpdate, _ctx): Promise<AgentToolResult> {
        let timeoutId: ReturnType<typeof setTimeout> | null = null;
        let abortHandler: (() => void) | null = null;

        const callPromise = client.callTool({ name: tool.name, arguments: params as Record<string, unknown> });

        const timeoutPromise = new Promise<never>((_, reject) => {
          timeoutId = setTimeout(
            () => reject(new Error(`MCP tool ${piName} timed out after ${TOOL_CALL_TIMEOUT_MS / 1000}s`)),
            TOOL_CALL_TIMEOUT_MS,
          );
        });

        const abortPromise = new Promise<never>((_, reject) => {
          abortHandler = () => reject(new Error(`MCP tool ${piName} aborted`));
          signal?.addEventListener("abort", abortHandler);
        });

        try {
          const result = await Promise.race([callPromise, timeoutPromise, abortPromise]);

          const content = (result.content as Array<{ type: string; text?: string; mimeType?: string }>).map(
            (item) => {
              if (item.type === "text") {
                return { type: "text" as const, text: item.text ?? "" };
              }
              return {
                type: "text" as const,
                text: `[${item.type} content${item.mimeType ? ` (${item.mimeType})` : ""}]`,
              };
            },
          );

          return { content, isError: result.isError === true };
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          return {
            content: [{ type: "text" as const, text: `MCP error: ${msg}` }],
            isError: true,
          };
        } finally {
          if (timeoutId !== null) clearTimeout(timeoutId);
          if (abortHandler !== null) signal?.removeEventListener("abort", abortHandler);
        }
      },
    });
  }
}
