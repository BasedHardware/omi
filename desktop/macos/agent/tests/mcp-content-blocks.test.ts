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
  return new McpHttpClient("https://example.test/mcp", undefined, fetchImpl);
}

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

  it("raises a tool error with its own text", async () => {
    const client = clientReturning({ content: [{ type: "text", text: "quota exceeded" }], isError: true });
    await expect(client.callTool("query", {})).rejects.toThrow("quota exceeded");
  });
});
