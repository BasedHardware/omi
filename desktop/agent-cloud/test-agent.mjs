import { query, tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import Database from "better-sqlite3";
import { z } from "zod";
import { homedir } from "os";
import { join } from "path";

const DB_PATH = process.env.DB_PATH;
const BACKEND_URL = process.env.BACKEND_URL || "https://api.omi.me";
const FIREBASE_TOKEN = process.env.FIREBASE_TOKEN;

// Open DB
const db = Database(DB_PATH, { readonly: true });
db.pragma("journal_mode = WAL");

// Simple SQL tool
const executeSqlTool = tool(
  "execute_sql",
  "Run SQL on the user's omi.db SQLite database. SELECT only, auto-limits to 200 rows.",
  { query: z.string().describe("SQL query to execute") },
  async ({ query: sqlQuery }) => {
    try {
      let q = sqlQuery;
      if (!/\bLIMIT\b/i.test(q)) q = q.replace(/;?\s*$/, " LIMIT 200");
      const rows = db.prepare(q).all();
      return { content: [{ type: "text", text: JSON.stringify({ rows, count: rows.length }) }] };
    } catch (err) {
      return { content: [{ type: "text", text: JSON.stringify({ error: err.message }) }] };
    }
  }
);

// JSON Schema → Zod converter
function jsonSchemaToZod(schema) {
  const props = schema.properties || {};
  const required = new Set(schema.required || []);
  const shape = {};
  for (const [name, prop] of Object.entries(props)) {
    if (name === "config") continue;
    let zodType;
    const rawType = prop.type || (prop.anyOf ? prop.anyOf.find(t => t.type && t.type !== "null")?.type : "string");
    switch (rawType) {
      case "integer": case "number": zodType = z.number(); break;
      case "boolean": zodType = z.boolean(); break;
      case "array": zodType = z.array(z.any()); break;
      default: zodType = z.string();
    }
    if (prop.description) zodType = zodType.describe(prop.description);
    if (!required.has(name)) {
      zodType = zodType.optional();
      if (prop.default !== undefined) zodType = zodType.default(prop.default);
    }
    shape[name] = zodType;
  }
  return shape;
}

// Fetch backend tools
console.log("Fetching backend tools...");
const resp = await fetch(`${BACKEND_URL}/v1/agent/tools`, {
  headers: { Authorization: `Bearer ${FIREBASE_TOKEN}` },
});
const data = await resp.json();
const toolDefs = data.tools || [];
console.log(`Fetched ${toolDefs.length} tools from backend`);

const backendTools = toolDefs.map((def) => {
  const zodShape = jsonSchemaToZod(def.parameters || {});
  return tool(
    def.name,
    def.description || `Backend tool: ${def.name}`,
    zodShape,
    async (params) => {
      try {
        const execResp = await fetch(`${BACKEND_URL}/v1/agent/execute-tool`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${FIREBASE_TOKEN}`,
          },
          body: JSON.stringify({ tool_name: def.name, params }),
        });
        const result = await execResp.json();
        if (result.error) return { content: [{ type: "text", text: `Error: ${result.error}` }] };
        return { content: [{ type: "text", text: result.result || JSON.stringify(result) }] };
      } catch (err) {
        return { content: [{ type: "text", text: `Error calling ${def.name}: ${err.message}` }] };
      }
    }
  );
});

const allTools = [executeSqlTool, ...backendTools];
console.log(`Total tools: ${allTools.length}`);

const omiServer = createSdkMcpServer({
  name: "omi-tools",
  tools: allTools,
});

// Run a test query (CLI mode, no Playwright)
const prompt = process.argv[2] || "List my first 3 action items briefly.";
console.log(`\nQuery: ${prompt}\n`);

const abortController = new AbortController();
const q = query({
  prompt,
  options: {
    model: "claude-sonnet-4-6",
    abortController,
    systemPrompt: "You are an AI assistant. Use the available tools to answer the user's question. Be concise.",
    permissionMode: "bypassPermissions",
    allowDangerouslySkipPermissions: true,
    maxTurns: 3,
    cwd: process.env.HOME || "/",
    mcpServers: {
      "omi-tools": omiServer,
    },
  },
});

for await (const message of q) {
  if (message.type === "stream_event") {
    const event = message.event;
    if (event?.type === "content_block_delta" && event.delta?.type === "text_delta") {
      process.stdout.write(event.delta.text);
    }
  } else if (message.type === "result") {
    console.log(`\n\n[Done — cost: $${(message.total_cost_usd || 0).toFixed(4)}]`);
    break;
  }
}

db.close();
