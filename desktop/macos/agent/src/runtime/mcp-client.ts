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

export abstract class McpClient {
  /** What `initialize` said the server offers. Empty until the handshake runs. */
  private capabilities: Record<string, unknown> = {};

  /** Called by each transport with the `initialize` result. */
  protected recordCapabilities(result: unknown): void {
    const declared = (result as { capabilities?: unknown } | undefined)?.capabilities;
    this.capabilities =
      declared && typeof declared === "object" ? (declared as Record<string, unknown>) : {};
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

  /**
   * A tool's result as the blocks a model turn carries. Text is joined the way
   * it always was; an image survives as an image when it is one the model can
   * actually read, so a screen-capture server answers with the picture instead
   * of a note that a picture happened.
   */
  async callTool(name: string, args: Record<string, unknown>): Promise<McpToolBlock[]> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/call", { name, arguments: args })) as McpToolResult;
    const blocks = renderContent(result?.content ?? [], { images: true });
    if (result?.isError) {
      throw new Error(textOf(blocks) || `MCP tool ${name} reported an error`);
    }
    if (blocks.length > 0) return blocks;
    // Structured output (spec 2025-06-18) is a tool's answer when it has no
    // prose to go with it; a server that returns only this used to fall through
    // to the raw envelope.
    if (result?.structuredContent !== undefined) {
      return [{ type: "text", text: JSON.stringify(result.structuredContent) }];
    }
    return [{ type: "text", text: `Tool ${name} returned no readable content.` }];
  }
}

interface McpToolResult {
  content?: unknown[];
  structuredContent?: unknown;
  isError?: boolean;
}

/** A block of a tool result, in the shape a model turn carries it. */
export type McpToolBlock =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };

/** The image types a model turn can carry; anything else is named, not sent. */
const MODEL_READABLE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);

/**
 * Base64 budget for one passed-through image. The Claude API takes 10 MB of
 * base64 per image directly and 5 MB through Bedrock and Vertex, so 5 MB is the
 * figure that holds everywhere. A full Retina screen capture lands under it as
 * PNG; anything larger is a server sending something other than a screenshot.
 */
const MAX_IMAGE_BASE64_CHARS = 5_000_000;

/** Images per result. A capture server answering with a frame per display is fine; a film is not. */
const MAX_IMAGES_PER_RESULT = 4;

/**
 * Tool result content as blocks.
 *
 * Only `text` blocks used to survive, and a result made only of images fell
 * through to `JSON.stringify(result)` — which put the entire base64 payload into
 * the conversation. Images now pass through within a size and count budget;
 * everything else that is not text is *named*, so the model learns what came
 * back and can ask for it another way, and the context stays readable.
 *
 * `images: false` names images too. Prompt expansion reads that way: it returns
 * one string, and its images are illustrations of a template rather than the
 * answer a capture tool was called for.
 */
function renderContent(blocks: unknown[], options: { images: boolean }): McpToolBlock[] {
  const rendered: McpToolBlock[] = [];
  let imagesKept = 0;
  const push = (text: string) => {
    if (text) rendered.push({ type: "text", text });
  };
  for (const raw of blocks) {
    const block = (raw ?? {}) as Record<string, unknown>;
    const mime = typeof block.mimeType === "string" ? block.mimeType : "";
    switch (block.type) {
      case "text":
        push(typeof block.text === "string" ? block.text : "");
        break;
      case "image": {
        const data = typeof block.data === "string" ? block.data : "";
        const sendable =
          options.images &&
          data.length > 0 &&
          data.length <= MAX_IMAGE_BASE64_CHARS &&
          MODEL_READABLE_IMAGE_TYPES.has(mime) &&
          imagesKept < MAX_IMAGES_PER_RESULT;
        if (sendable) {
          rendered.push({ type: "image", data, mimeType: mime });
          imagesKept += 1;
        } else {
          push(`[image: ${mime || "unknown type"}, not shown]`);
        }
        break;
      }
      case "audio":
        push(`[audio: ${mime || "unknown type"}, not shown]`);
        break;
      case "resource_link": {
        const uri = typeof block.uri === "string" ? block.uri : "";
        const label = typeof block.name === "string" && block.name ? block.name : uri;
        push(uri ? `[resource: ${label} — ${uri}]` : "");
        break;
      }
      case "resource": {
        // An embedded resource carries the text inline when it has any.
        const resource = (block.resource ?? {}) as Record<string, unknown>;
        if (typeof resource.text === "string") {
          push(resource.text);
          break;
        }
        const uri = typeof resource.uri === "string" ? resource.uri : "";
        push(uri ? `[resource: ${uri}, not shown]` : "");
        break;
      }
      default:
        break;
    }
  }
  return rendered;
}

/** The readable text of a rendered result, images named by their absence. */
export function textOf(blocks: McpToolBlock[]): string {
  return blocks
    .flatMap((block) => (block.type === "text" ? [block.text] : []))
    .filter(Boolean)
    .join("\n");
}

/** A block list rendered as one string, for surfaces that carry no images. */
function describeContent(blocks: unknown[]): string {
  return textOf(renderContent(blocks, { images: false }));
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
