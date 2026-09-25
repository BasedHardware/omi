import { describe, expect, it } from "vitest";

import { McpHttpClient } from "../src/runtime/mcp-http-client.js";

/** A Streamable HTTP server that answers tools/call with a fixed result. */
function clientReturning(result: unknown): McpHttpClient {
  const fetchImpl = (async (_url: string, init: { body: string }) => {
    const message = JSON.parse(init.body) as { id?: number; method: string };
    const body =
      message.method === "initialize"
        ? { protocolVersion: "2025-06-18", capabilities: { tools: {} } }
        : result;
    return new Response(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: body }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as unknown as typeof fetch;
  return new McpHttpClient("https://example.test/mcp", {}, fetchImpl);
}

describe("MCP request headers", () => {
  // The loader builds an Authorization header from a `token` or a stored OAuth
  // access_token; the caller used to unwrap it and the client rebuilt it as
  // `Bearer <value>`, which corrupted any scheme that was not Bearer.
  it("sends configured headers verbatim, whatever the scheme", async () => {
    const seen: Array<Record<string, string>> = [];
    const fetchImpl = (async (_url: string, init: { body: string; headers: Record<string, string> }) => {
      seen.push(init.headers);
      const message = JSON.parse(init.body) as { id?: number };
      return new Response(JSON.stringify({ jsonrpc: "2.0", id: message.id, result: { tools: [] } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;

    const client = new McpHttpClient(
      "https://example.test/mcp",
      { Authorization: "Basic dXNlcjpwYXNz", "X-Api-Key": "k1" },
      fetchImpl,
    );
    await client.listTools();
    expect(seen[0].Authorization).toBe("Basic dXNlcjpwYXNz");
    expect(seen[0]["X-Api-Key"]).toBe("k1");
  });
});

describe("MCP tool result content", () => {
  // A screenshot tool returned no text blocks, so the old code fell through to
  // JSON.stringify(result) and put the whole base64 payload into the context.
  it("names an image instead of dumping its payload", async () => {
    const client = clientReturning({
      content: [
        { type: "text", text: "Captured the page." },
        { type: "image", mimeType: "image/png", data: "iVBORw0KGgoAAAA".repeat(500) },
      ],
    });
    const text = await client.callTool("screenshot", {});
    expect(text).toBe("Captured the page.\n[image: image/png, not shown]");
    expect(text).not.toContain("iVBORw0KGgo");
  });

  it("keeps a resource link addressable and inlines an embedded resource's text", async () => {
    const client = clientReturning({
      content: [
        { type: "resource_link", name: "report.csv", uri: "file:///tmp/report.csv" },
        { type: "resource", resource: { uri: "file:///tmp/a.md", text: "# Notes" } },
        { type: "audio", mimeType: "audio/wav", data: "UklGRg==" },
      ],
    });
    expect(await client.callTool("fetch", {})).toBe(
      "[resource: report.csv — file:///tmp/report.csv]\n# Notes\n[audio: audio/wav, not shown]",
    );
  });

  // Structured output is the whole answer for a tool with no prose to go with it.
  it("returns structured output when there is no content to read", async () => {
    const client = clientReturning({ content: [], structuredContent: { total: 42 } });
    expect(await client.callTool("count", {})).toBe('{"total":42}');
  });

  it("says so rather than dumping the envelope when nothing is readable", async () => {
    const client = clientReturning({ content: [{ type: "video", data: "x" }] });
    expect(await client.callTool("render", {})).toBe("Tool render returned no readable content.");
  });

  // A prompt's messages carry the same block types a tool result does. They used
  // to go through a text-only reader, so `resource-prompt` — a prompt whose whole
  // point is the resource it carries — expanded to its preamble and nothing else.
  it("names a resource a prompt carries instead of dropping it", async () => {
    const client = clientReturning({
      messages: [
        { role: "user", content: { type: "text", text: "Analyze this:" } },
        { role: "user", content: { type: "resource", resource: { uri: "demo://blob/1", blob: "AAAA" } } },
      ],
    });
    expect(await client.getPrompt("resource-prompt", {})).toBe(
      "user: Analyze this:\n\nuser: [resource: demo://blob/1, not shown]",
    );
  });

  // Older servers send a message's content as a bare string rather than a block.
  it("reads a prompt message whose content is a plain string", async () => {
    const client = clientReturning({ messages: [{ role: "user", content: "just text" }] });
    expect(await client.getPrompt("simple", {})).toBe("user: just text");
  });

  it("raises a tool error with its own text", async () => {
    const client = clientReturning({ content: [{ type: "text", text: "quota exceeded" }], isError: true });
    await expect(client.callTool("query", {})).rejects.toThrow("quota exceeded");
  });
});
