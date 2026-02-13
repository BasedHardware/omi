#!/usr/bin/env node
import { query, tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import Database from "better-sqlite3";
import { z } from "zod";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// --- Configuration ---
const DB_PATH = process.env.DB_PATH || "/home/matthewdi/omi-agent/data/omi.db";
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const EMBEDDING_DIM = 3072;

const __dirname = dirname(fileURLToPath(import.meta.url));
const playwrightCli = join(__dirname, "node_modules", "@playwright", "mcp", "cli.js");

// --- Database Setup ---
const db = Database(DB_PATH, { readonly: true });
db.pragma("journal_mode = WAL");

// Get schema for system prompt
function getSchema() {
  const tables = db
    .prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'grdb_%' ORDER BY name"
    )
    .all();

  let schema = "";
  for (const { name } of tables) {
    const cols = db.prepare(`PRAGMA table_info('${name}')`).all();
    const colDefs = cols.map((c) => `  ${c.name} ${c.type}`).join("\n");
    schema += `\n${name}:\n${colDefs}\n`;
    const count = db.prepare(`SELECT COUNT(*) as n FROM "${name}"`).get();
    schema += `  (${count.n} rows)\n`;
  }
  return schema;
}

// --- SQL Execution Logic ---
const BLOCKED_KEYWORDS = ["DROP", "ALTER", "CREATE", "PRAGMA", "ATTACH", "DETACH", "VACUUM"];

function executeSqlQuery(sqlQuery) {
  const upper = sqlQuery.toUpperCase();
  for (const kw of BLOCKED_KEYWORDS) {
    if (new RegExp(`\\b${kw}\\b`).test(upper)) {
      return JSON.stringify({ error: `Blocked: ${kw} statements not allowed` });
    }
  }
  if (/;\s*\S/.test(sqlQuery)) {
    return JSON.stringify({ error: "Multi-statement queries not allowed" });
  }
  const trimmed = upper.trim();
  if ((trimmed.startsWith("UPDATE") || trimmed.startsWith("DELETE")) && !upper.includes("WHERE")) {
    return JSON.stringify({ error: "UPDATE/DELETE require a WHERE clause" });
  }
  try {
    if (trimmed.startsWith("SELECT")) {
      let execQuery = sqlQuery;
      if (!/\bLIMIT\b/i.test(sqlQuery)) {
        execQuery = sqlQuery.replace(/;?\s*$/, " LIMIT 200");
      }
      const rows = db.prepare(execQuery).all();
      return JSON.stringify({ rows, count: rows.length });
    } else {
      return JSON.stringify({ error: "Database is in read-only mode (cloud copy)" });
    }
  } catch (err) {
    return JSON.stringify({ error: err.message });
  }
}

// --- Semantic Search Logic ---
async function embedQueryText(text) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=${GEMINI_API_KEY}`;
  const body = {
    model: "models/gemini-embedding-001",
    content: { parts: [{ text }] },
    taskType: "RETRIEVAL_QUERY",
  };
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await resp.json();
  if (!json.embedding?.values) {
    throw new Error(`Embedding API error: ${JSON.stringify(json.error || json)}`);
  }
  const raw = json.embedding.values.map(Number);
  let norm = 0;
  for (const v of raw) norm += v * v;
  norm = Math.sqrt(norm);
  return norm > 0 ? raw.map((v) => v / norm) : raw;
}

function readEmbeddingFromBlob(buffer) {
  if (buffer.byteLength !== EMBEDDING_DIM * 4) return null;
  return new Float32Array(buffer.buffer, buffer.byteOffset, EMBEDDING_DIM);
}

async function performSemanticSearch(searchQuery, days = 7, appFilter = null) {
  if (!GEMINI_API_KEY) {
    return JSON.stringify({ error: "GEMINI_API_KEY not set" });
  }
  const queryEmbedding = await embedQueryText(searchQuery);
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);
  const startStr = startDate.toISOString().replace("T", " ").slice(0, 19);

  let sql = `SELECT id, timestamp, appName, windowTitle, substr(ocrText, 1, 300) as ocrPreview, embedding
             FROM screenshots WHERE embedding IS NOT NULL AND timestamp >= ?`;
  const params = [startStr];
  if (appFilter) {
    sql += " AND appName = ?";
    params.push(appFilter);
  }
  sql += " ORDER BY timestamp DESC";

  const rows = db.prepare(sql).all(...params);
  const results = [];
  for (const row of rows) {
    const stored = readEmbeddingFromBlob(row.embedding);
    if (!stored) continue;
    let dot = 0;
    for (let i = 0; i < queryEmbedding.length; i++) dot += queryEmbedding[i] * stored[i];
    if (dot > 0.3) {
      results.push({
        screenshotId: row.id,
        similarity: Math.round(dot * 1000) / 1000,
        timestamp: row.timestamp,
        appName: row.appName,
        windowTitle: row.windowTitle,
        ocrPreview: row.ocrPreview,
      });
    }
  }
  results.sort((a, b) => b.similarity - a.similarity);
  return JSON.stringify({
    query: searchQuery,
    days,
    totalScanned: rows.length,
    matchesAboveThreshold: results.length,
    results: results.slice(0, 15),
  });
}

// --- Define MCP Tools using Agent SDK ---

const executeSqlTool = tool(
  "execute_sql",
  `Run SQL on the user's omi.db SQLite database.
Supports: SELECT, INSERT, UPDATE, DELETE.
SELECT auto-limits to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE blocked.
Use for: app usage stats, time queries, task management, aggregations, anything structured.`,
  { query: z.string().describe("SQL query to execute") },
  async ({ query }) => {
    const result = executeSqlQuery(query);
    return { content: [{ type: "text", text: result }] };
  }
);

const semanticSearchTool = tool(
  "semantic_search",
  `Vector similarity search on screen history.
Use for: fuzzy conceptual queries where exact SQL keywords won't work.
e.g. "reading about machine learning", "working on design mockups"`,
  {
    query: z.string().describe("Natural language search query"),
    days: z.number().optional().default(7).describe("Number of days to search back (default: 7)"),
    app_filter: z.string().optional().describe("Filter results to a specific app name"),
  },
  async ({ query, days, app_filter }) => {
    const result = await performSemanticSearch(query, days, app_filter);
    return { content: [{ type: "text", text: result }] };
  }
);

// Create MCP server for OMI tools
const omiServer = createSdkMcpServer({
  name: "omi-tools",
  tools: [executeSqlTool, semanticSearchTool],
});

// --- Build System Prompt ---

const schema = getSchema();
const systemPrompt = `You are an AI assistant with access to the user's OMI desktop database.
This database contains their screen history (screenshots with OCR text), tasks, transcriptions, memories, and focus sessions.

DATABASE SCHEMA:
${schema}

TOOLS:
- **execute_sql**: Run SQL queries on the database. SELECT auto-limits to 200 rows. Use for structured queries (app usage, time ranges, task management, aggregations).
- **semantic_search**: Vector similarity search on screenshot OCR text. Use for fuzzy/conceptual queries where exact keywords won't work.
- **Playwright browser tools**: You can navigate websites, click elements, fill forms, take screenshots, etc. Use when the user asks you to do something on the web.

GUIDELINES:
- Use datetime functions for time queries: datetime('now', '-1 day', 'localtime'), datetime('now', 'start of day', 'localtime')
- Screenshots have: timestamp, appName, windowTitle, ocrText, embedding
- Action items have: description, completed, deleted, priority, category, source, dueAt, createdAt
- Transcription sessions have: title, overview, startedAt, finishedAt, source
- For "what did I do today/yesterday" queries, use screenshots table grouped by appName
- For task queries, use action_items table
- For conversation queries, use transcription_sessions + transcription_segments
- Be concise and helpful. Format results clearly.`;

// --- Run Agent ---

async function runAgent(userMessage) {
  console.log(`\n${"=".repeat(60)}`);
  console.log(`User: ${userMessage}`);
  console.log("=".repeat(60));

  const options = {
    model: "claude-opus-4-6",
    systemPrompt,
    allowedTools: [
      "Read",
      "Write",
      "Edit",
      "Bash",
      "Glob",
      "Grep",
      "WebSearch",
      "WebFetch",
    ],
    permissionMode: "bypassPermissions",
    allowDangerouslySkipPermissions: true,
    maxTurns: 15,
    cwd: process.env.HOME || "/",
    mcpServers: {
      "omi-tools": omiServer,
      "playwright": {
        command: process.execPath,
        args: [
          playwrightCli,
          "--user-data-dir", join(__dirname, "chrome-profile"),
          "--headless",
          "--no-sandbox",
        ],
      },
    },
  };

  let fullText = "";

  const q = query({ prompt: userMessage, options });

  for await (const message of q) {
    switch (message.type) {
      case "system":
        if ("session_id" in message) {
          console.log(`[Session: ${message.session_id}]`);
        }
        break;

      case "stream_event": {
        const event = message.event;
        if (event?.type === "content_block_start" && event.content_block?.type === "tool_use") {
          console.log(`\n[Tool started: ${event.content_block.name}]`);
        }
        if (event?.type === "content_block_delta" && event.delta?.type === "text_delta") {
          const text = event.delta.text;
          fullText += text;
          process.stdout.write(text);
        }
        break;
      }

      case "assistant": {
        const content = message.message?.content;
        if (Array.isArray(content)) {
          for (const block of content) {
            if (block.type === "tool_use") {
              console.log(`\n[Tool: ${block.name}(${JSON.stringify(block.input).slice(0, 200)})]`);
            }
          }
        }
        break;
      }

      case "result": {
        if (message.subtype === "success") {
          const cost = message.total_cost_usd || 0;
          // Print the final result text which includes the full response
          if (message.result && message.result !== fullText) {
            // Only print the part we haven't streamed yet
            const newText = fullText ? message.result.replace(fullText, "") : message.result;
            if (newText.trim()) {
              process.stdout.write(newText);
            }
          }
          console.log(`\n\n[Done — cost: $${cost.toFixed(4)}]`);
        } else {
          console.error(`\n[Agent error (${message.subtype}): ${(message.errors || []).join(", ")}]`);
        }
        break;
      }
    }
  }

  console.log("");
}

// --- CLI ---
const userQuery = process.argv.slice(2).join(" ");
if (!userQuery) {
  console.log("Usage: node agent.mjs <your question>");
  console.log('Example: node agent.mjs "What did I do today?"');
  console.log('Example: node agent.mjs "Find where I was reading about AI"');
  console.log('Example: node agent.mjs "Go to omi.me and take a screenshot"');
  process.exit(0);
}

await runAgent(userQuery);
db.close();
