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

export abstract class McpClient {
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
