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
    const result = (await this.rpc("tools/list", {})) as { tools?: unknown };
    if (!Array.isArray(result?.tools)) return [];
    return result.tools.flatMap((tool) => {
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

  /** The server's published prompts, or none when it publishes no such capability. */
  async listPrompts(): Promise<McpPrompt[]> {
    await this.ensureInitialized();
    if (!this.supports("prompts")) return [];
    const result = (await this.rpc("prompts/list", {})) as { prompts?: unknown };
    if (!Array.isArray(result?.prompts)) return [];
    return result.prompts.flatMap((prompt) => {
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
      const text = textOf(message?.content);
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
    const result = (await this.rpc("tools/call", { name, arguments: args })) as {
      content?: Array<{ type?: string; text?: string }>;
      isError?: boolean;
    };
    const text = (result?.content ?? [])
      .filter((block) => block?.type === "text" && typeof block.text === "string")
      .map((block) => block.text)
      .join("\n");
    if (result?.isError) {
      throw new Error(text || `MCP tool ${name} reported an error`);
    }
    return text || JSON.stringify(result ?? {});
  }
}

/** The text carried by a content block, or by a list of them. */
function textOf(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map(textOf).filter(Boolean).join("\n");
  const block = content as { type?: string; text?: string } | undefined;
  return block?.type === "text" && typeof block.text === "string" ? block.text : "";
}
