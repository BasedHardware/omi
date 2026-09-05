/**
 * The MCP wire subset every user-added server is driven through, independent of
 * transport. Each transport supplies `rpc`; the tool surface is defined once
 * here so a fix to schema handling or result decoding lands for all of them.
 */

export interface McpRemoteTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export const MCP_PROTOCOL_VERSION = "2025-06-18";

export const MCP_CLIENT_INFO = { name: "omi-desktop", version: "1.0.0" };

/**
 * A prompt the server publishes: a named, argument-taking template it expands
 * into messages. Servers put their real workflows here — "review this PR",
 * "summarize this incident" — which a tools-only client never sees.
 */
export interface McpPrompt {
  name: string;
  description: string;
  arguments: Array<{ name: string; description: string; required: boolean }>;
}

/** Page budget for a cursor-paginated list; far past any real server's tool count. */
const MAX_LIST_PAGES = 50;

/** First line of a string, capped, or undefined when it is not a usable string. */
function firstLine(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const line = value.split("\n", 1)[0].trim().slice(0, 120);
  return line || undefined;
}

export abstract class McpClient {
  /** What `initialize` said the server offers. Empty until the handshake runs. */
  private capabilities: Record<string, unknown> = {};

  /** One-line server description from the handshake, for the discovery index. */
  private serverHint = "";

  /** Called by each transport with the `initialize` result. */
  protected recordCapabilities(result: unknown): void {
    const declared = (result as { capabilities?: unknown } | undefined)?.capabilities;
    this.capabilities =
      declared && typeof declared === "object" ? (declared as Record<string, unknown>) : {};
    // `instructions` is the server's own "how to use me"; `title` is its human
    // name. Either beats the raw server key, which is often a slug.
    const result_ = (result ?? {}) as {
      instructions?: unknown;
      serverInfo?: { title?: unknown };
    };
    this.serverHint =
      firstLine(result_.instructions) ?? firstLine(result_.serverInfo?.title) ?? "";
  }

  /** One-line server description, or "" when the server declares none. */
  get serverDescription(): string {
    return this.serverHint;
  }

  /**
   * Whether the server declared a capability. Asking a server for prompts it
   * does not have is an error response per connection, every session.
   */
  supports(capability: "tools" | "prompts" | "resources"): boolean {
    return Boolean(this.capabilities[capability]);
  }

  /** One JSON-RPC round trip. Rejects on transport failure or a JSON-RPC error. */
  protected abstract rpc(method: string, params: Record<string, unknown>): Promise<unknown>;

  /** Handshake, run once and reused; transports differ in how they open. */
  protected abstract ensureInitialized(): Promise<void>;

  dispose(): void {}

  async listTools(): Promise<McpRemoteTool[]> {
    await this.ensureInitialized();
    const pages = await this.pages("tools/list", "tools");
    return pages.flatMap((tool) => {
      const { name, description, inputSchema } = (tool ?? {}) as Record<string, unknown>;
      if (typeof name !== "string" || !name) return [];
      return [
        {
          name,
          description: typeof description === "string" ? description : "",
          inputSchema:
            inputSchema && typeof inputSchema === "object"
              ? (inputSchema as Record<string, unknown>)
              : { type: "object", properties: {} },
        },
      ];
    });
  }

  /**
   * Every page of a cursor-paginated list method. A server with more entries
   * than its page size returns a `nextCursor`; ignoring it silently truncated
   * the list, and the missing tools simply did not exist as far as chat knew.
   *
   * Bounded twice over, because the cursor is the server's to choose: a page
   * budget, and a repeated cursor treated as the end rather than looped on.
   */
  private async pages(method: string, key: string): Promise<unknown[]> {
    const collected: unknown[] = [];
    const seen = new Set<string>();
    let cursor: string | undefined;
    for (let page = 0; page < MAX_LIST_PAGES; page += 1) {
      const result = (await this.rpc(method, cursor ? { cursor } : {})) as Record<string, unknown>;
      const entries = result?.[key];
      if (!Array.isArray(entries)) break;
      collected.push(...entries);
      const next = result.nextCursor;
      if (typeof next !== "string" || !next || seen.has(next)) break;
      seen.add(next);
      cursor = next;
    }
    return collected;
  }

  /** The server's published prompts, or none when it publishes no such capability. */
  async listPrompts(): Promise<McpPrompt[]> {
    await this.ensureInitialized();
    if (!this.supports("prompts")) return [];
    const pages = await this.pages("prompts/list", "prompts");
    return pages.flatMap((prompt) => {
      const { name, description, arguments: args } = (prompt ?? {}) as Record<string, unknown>;
      if (typeof name !== "string" || !name) return [];
      const parsed = (Array.isArray(args) ? args : []).flatMap((argument) => {
        const entry = (argument ?? {}) as Record<string, unknown>;
        if (typeof entry.name !== "string" || !entry.name) return [];
        return [
          {
            name: entry.name,
            description: typeof entry.description === "string" ? entry.description : "",
            required: entry.required === true,
          },
        ];
      });
      return [
        {
          name,
          description: typeof description === "string" ? description : "",
          arguments: parsed,
        },
      ];
    });
  }

  /** One prompt expanded with its arguments, flattened to the text it carries. */
  async getPrompt(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInitialized();
    const result = (await this.rpc("prompts/get", { name, arguments: args })) as {
      description?: string;
      messages?: Array<{ role?: string; content?: unknown }>;
    };
    const parts = (result?.messages ?? []).flatMap((message) => {
      const text = describeContent(blocksOf(message?.content));
      if (!text) return [];
      // Prompts carry a conversation; the roles are what make it one.
      return [message?.role ? `${message.role}: ${text}` : text];
    });
    const body = parts.join("\n\n");
    if (body) return body;
    return result?.description || `Prompt ${name} returned no content.`;
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/call", { name, arguments: args })) as McpToolResult;
    const text = describeContent(result?.content ?? []);
    if (result?.isError) {
      throw new Error(text || `MCP tool ${name} reported an error`);
    }
    if (text) return text;
    // Structured output (spec 2025-06-18) is a tool's answer when it has no
    // prose to go with it; a server that returns only this used to fall through
    // to the raw envelope.
    if (result?.structuredContent !== undefined) {
      return JSON.stringify(result.structuredContent);
    }
    return `Tool ${name} returned no readable content.`;
  }
}

interface McpToolResult {
  content?: unknown[];
  structuredContent?: unknown;
  isError?: boolean;
}

/**
 * A tool result rendered as text.
 *
 * Only `text` blocks used to survive, and a result made only of images fell
 * through to `JSON.stringify(result)` — which put the entire base64 payload into
 * the conversation. Non-text blocks are named instead: the model learns what
 * came back and can ask for it another way, and the context stays readable.
 */
function describeContent(blocks: unknown[]): string {
  return blocks
    .map((raw) => {
      const block = (raw ?? {}) as Record<string, unknown>;
      switch (block.type) {
        case "text":
          return typeof block.text === "string" ? block.text : "";
        case "image":
        case "audio": {
          const mime = typeof block.mimeType === "string" ? block.mimeType : "unknown type";
          return `[${block.type}: ${mime}, not shown]`;
        }
        case "resource_link": {
          const uri = typeof block.uri === "string" ? block.uri : "";
          const label = typeof block.name === "string" && block.name ? block.name : uri;
          return uri ? `[resource: ${label} — ${uri}]` : "";
        }
        case "resource": {
          // An embedded resource carries the text inline when it has any.
          const resource = (block.resource ?? {}) as Record<string, unknown>;
          if (typeof resource.text === "string") return resource.text;
          const uri = typeof resource.uri === "string" ? resource.uri : "";
          return uri ? `[resource: ${uri}, not shown]` : "";
        }
        default:
          return "";
      }
    })
    .filter(Boolean)
    .join("\n");
}

/**
 * A prompt message's content as blocks. The spec allows one block or a list,
 * and older servers send a bare string; all three become the block list
 * `describeContent` renders, so a prompt carrying an image or a resource is
 * named rather than dropped the way a tool result's would not be.
 */
function blocksOf(content: unknown): unknown[] {
  if (typeof content === "string") return [{ type: "text", text: content }];
  return Array.isArray(content) ? content : [content];
}
