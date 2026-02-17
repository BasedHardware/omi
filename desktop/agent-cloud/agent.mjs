#!/usr/bin/env node
import { query, tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import Database from "better-sqlite3";
import { z } from "zod";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { createServer } from "http";
import { WebSocketServer } from "ws";
import { existsSync, mkdirSync, createWriteStream, statSync, renameSync, unlinkSync } from "fs";
import { createInflateRaw, createGunzip } from "zlib";
import { homedir } from "os";

// --- Configuration ---
const DB_PATH = process.env.DB_PATH || join(homedir(), "omi-agent/data/omi.db");
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const AUTH_TOKEN = process.env.AUTH_TOKEN;
const PORT = parseInt(process.env.PORT || "8080", 10);
const EMBEDDING_DIM = 3072;
// Max upload size: 10GB
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024 * 1024;

// Tables allowed for incremental sync from desktop
const SYNC_TABLES = new Set([
  "screenshots", "action_items", "transcription_sessions",
  "transcription_segments", "memories", "staged_tasks",
  "focus_sessions", "observations", "live_notes",
  "ai_user_profiles", "task_dedup_log",
]);


const __dirname = dirname(fileURLToPath(import.meta.url));
const playwrightCli = join(__dirname, "node_modules", "@playwright", "mcp", "cli.js");

// --- Database Setup (lazy — opened on first use or after upload) ---
let db = null;
let defaultSystemPrompt = null;
let omiServer = null;

function openDatabase() {
  if (db) {
    try { db.close(); } catch {}
    db = null;
  }
  if (!existsSync(DB_PATH)) {
    return false;
  }
  db = Database(DB_PATH);  // writable for /sync inserts; agent tool still blocks non-SELECT
  db.pragma("journal_mode = WAL");

  // Rebuild schema + system prompt + MCP server
  const schema = getSchema();
  defaultSystemPrompt = `You are an AI assistant with access to the user's OMI desktop database.
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

  omiServer = createSdkMcpServer({
    name: "omi-tools",
    tools: [executeSqlTool, semanticSearchTool],
  });

  console.log(`[db] Database opened: ${DB_PATH}`);
  return true;
}

function isDatabaseReady() {
  return db !== null;
}

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
  if (!db) return JSON.stringify({ error: "Database not loaded. Upload omi.db first." });
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
  if (!db) return JSON.stringify({ error: "Database not loaded. Upload omi.db first." });
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

// --- Shared Agent Query Handler ---

async function handleQuery({ prompt, systemPrompt, cwd, send, abortController }) {
  if (!isDatabaseReady()) {
    send({ type: "error", message: "Database not available. Upload omi.db first." });
    return { text: "", sessionId: "", costUsd: 0 };
  }

  let sessionId = "";
  let fullText = "";
  let costUsd = 0;
  const pendingTools = [];

  const options = {
    model: "claude-opus-4-6",
    abortController,
    systemPrompt: systemPrompt || defaultSystemPrompt,
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
    cwd: cwd || process.env.HOME || "/",
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

  const q = query({ prompt, options });

  for await (const message of q) {
    if (abortController.signal.aborted) break;

    switch (message.type) {
      case "system":
        if ("session_id" in message) {
          sessionId = message.session_id;
          send({ type: "init", sessionId });
        }
        break;

      case "stream_event": {
        const event = message.event;

        if (event?.type === "content_block_start" && event.content_block?.type === "tool_use") {
          const name = event.content_block.name;
          pendingTools.push(name);
          send({ type: "tool_activity", name, status: "started" });
        }

        if (event?.type === "content_block_delta" && event.delta?.type === "text_delta") {
          if (pendingTools.length > 0) {
            for (const name of pendingTools) {
              send({ type: "tool_activity", name, status: "completed" });
            }
            pendingTools.length = 0;
          }
          const text = event.delta.text;
          fullText += text;
          send({ type: "text_delta", text });
        }
        break;
      }

      case "assistant": {
        // Fallback: if streaming didn't capture text (e.g. after tool calls),
        // extract it from the complete assistant message
        const content = message.message?.content;
        if (Array.isArray(content)) {
          for (const block of content) {
            if (block.type === "text" && typeof block.text === "string") {
              // Check if this text was already sent via stream_event deltas
              if (!fullText.includes(block.text)) {
                fullText += block.text;
                send({ type: "text_delta", text: block.text });
              }
            }
          }
        }
        break;
      }

      case "result": {
        for (const name of pendingTools) {
          send({ type: "tool_activity", name, status: "completed" });
        }
        pendingTools.length = 0;

        if (message.subtype === "success") {
          costUsd = message.total_cost_usd || 0;
          // Send any final text that wasn't captured during streaming
          if (message.result) {
            const remaining = message.result.replace(fullText, "").trim();
            if (remaining) {
              send({ type: "text_delta", text: remaining });
              fullText += remaining;
            }
          }
        } else {
          const errors = message.errors || [];
          send({ type: "error", message: `Agent error (${message.subtype}): ${errors.join(", ")}` });
        }
        break;
      }
    }
  }

  return { text: fullText, sessionId, costUsd };
}

// --- Mode: CLI ---

async function runCli(userMessage) {
  if (!openDatabase()) {
    console.error(`ERROR: Database not found at ${DB_PATH}`);
    process.exit(1);
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log(`User: ${userMessage}`);
  console.log("=".repeat(60));

  const abortController = new AbortController();
  const send = (msg) => {
    switch (msg.type) {
      case "init":
        console.log(`[Session: ${msg.sessionId}]`);
        break;
      case "text_delta":
        process.stdout.write(msg.text);
        break;
      case "tool_activity":
        console.log(`\n[Tool ${msg.status}: ${msg.name}]`);
        break;
      case "error":
        console.error(`\n[Error: ${msg.message}]`);
        break;
    }
  };

  const result = await handleQuery({ prompt: userMessage, send, abortController });
  console.log(`\n\n[Done — cost: $${result.costUsd.toFixed(4)}]`);
  db.close();
}

// --- Auth helper for HTTP endpoints ---

function verifyAuth(req) {
  const authHeader = req.headers["authorization"];
  const url = new URL(req.url, `http://${req.headers.host}`);
  const tokenParam = url.searchParams.get("token");
  const token = authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : tokenParam;
  return token === AUTH_TOKEN;
}

// --- Mode: WebSocket Server ---

function startServer() {
  const log = (msg) => console.log(`[server] ${msg}`);

  if (!AUTH_TOKEN) {
    console.error("ERROR: AUTH_TOKEN environment variable is required for server mode.");
    process.exit(1);
  }

  // Try to open DB if it exists (may not exist yet for fresh VMs)
  if (openDatabase()) {
    log("Database loaded at startup");
  } else {
    log(`Database not found at ${DB_PATH} — waiting for upload`);
  }

  // Ensure data directory exists for uploads
  const dataDir = dirname(DB_PATH);
  if (!existsSync(dataDir)) {
    mkdirSync(dataDir, { recursive: true });
  }

  const httpServer = createServer((req, res) => {
    // Health check endpoint (no auth)
    if (req.url === "/health" && req.method === "GET") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        status: "ok",
        uptime: process.uptime(),
        databaseReady: isDatabaseReady(),
      }));
      return;
    }

    // Database upload endpoint
    if (req.url?.startsWith("/upload") && req.method === "POST") {
      if (!verifyAuth(req)) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }

      const contentLength = parseInt(req.headers["content-length"] || "0", 10);
      if (contentLength > MAX_UPLOAD_BYTES) {
        res.writeHead(413, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "File too large", maxBytes: MAX_UPLOAD_BYTES }));
        return;
      }

      const encoding = (req.headers["content-encoding"] || "").toLowerCase();
      const isCompressed = encoding === "gzip" || encoding === "deflate" || encoding === "zlib";
      log(`Upload started (${(contentLength / 1024 / 1024).toFixed(1)} MB${isCompressed ? ", " + encoding + " compressed" : ""})`);

      // Write to temp file first, then rename (atomic)
      const tmpPath = DB_PATH + ".uploading";
      const stream = createWriteStream(tmpPath);
      let bytesReceived = 0;
      let aborted = false;

      // If compressed, pipe through decompressor
      let decompressor = null;
      if (encoding === "gzip") {
        decompressor = createGunzip();
      } else if (encoding === "deflate" || encoding === "zlib") {
        decompressor = createInflateRaw();
      }

      const writeTarget = decompressor || stream;

      if (decompressor) {
        decompressor.pipe(stream);
        decompressor.on("error", (err) => {
          log(`Upload decompression error: ${err.message}`);
          aborted = true;
          stream.destroy();
          try { unlinkSync(tmpPath); } catch {}
        });
      }

      stream.on("error", (err) => {
        log(`Upload stream error: ${err.message}`);
        aborted = true;
        try { unlinkSync(tmpPath); } catch {}
      });

      req.on("data", (chunk) => {
        if (aborted) return;
        bytesReceived += chunk.length;
        if (decompressor) {
          decompressor.write(chunk);
        } else {
          stream.write(chunk);
        }
      });

      const finalize = () => {
        // Close existing DB connection before replacing the file
        if (db) {
          try { db.close(); } catch {}
          db = null;
        }

        // Remove WAL/SHM files if they exist (stale from previous DB)
        try { unlinkSync(DB_PATH + "-wal"); } catch {}
        try { unlinkSync(DB_PATH + "-shm"); } catch {}

        // Atomic rename
        renameSync(tmpPath, DB_PATH);

        const finalSize = statSync(DB_PATH).size;
        log(`Upload complete: ${(bytesReceived / 1024 / 1024).toFixed(1)} MB received → ${(finalSize / 1024 / 1024).toFixed(1)} MB on disk`);

        // Re-open the database
        if (openDatabase()) {
          log("Database loaded after upload");
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({
            status: "ok",
            bytesReceived,
            finalSize,
            databaseReady: true,
          }));
        } else {
          log("ERROR: Failed to open database after upload");
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Failed to open uploaded database" }));
        }
      };

      req.on("end", () => {
        if (aborted) return;
        if (decompressor) {
          // End the decompressor; stream.end is called via pipe when decompressor finishes
          decompressor.end();
          stream.on("finish", finalize);
        } else {
          stream.end(finalize);
        }
      });

      req.on("error", (err) => {
        log(`Upload error: ${err.message}`);
        aborted = true;
        if (decompressor) decompressor.destroy();
        stream.destroy();
        try { unlinkSync(tmpPath); } catch {}
        if (!res.headersSent) {
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: err.message }));
        }
      });

      req.on("aborted", () => {
        log("Upload aborted by client");
        aborted = true;
        stream.destroy();
        try { unlinkSync(tmpPath); } catch {}
      });

      return;
    }

    // Incremental sync endpoint — desktop pushes new/changed rows
    if (req.url?.startsWith("/sync") && req.method === "POST") {
      if (!verifyAuth(req)) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }
      if (!db) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Database not loaded. Upload omi.db first." }));
        return;
      }

      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", () => {
        try {
          const payload = JSON.parse(body);
          const { table, rows } = payload;
          if (!table || !Array.isArray(rows) || rows.length === 0) {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: "Required: { table: string, rows: [{...}, ...] }" }));
            return;
          }
          if (!SYNC_TABLES.has(table)) {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: `Table '${table}' not in sync whitelist` }));
            return;
          }

          const cols = Object.keys(rows[0]);
          const placeholders = cols.map(() => "?").join(", ");
          const sql = `INSERT OR REPLACE INTO "${table}" (${cols.map(c => `"${c}"`).join(", ")}) VALUES (${placeholders})`;

          const stmt = db.prepare(sql);
          const insertMany = db.transaction((rowList) => {
            for (const row of rowList) {
              const values = cols.map((col) => {
                const val = row[col];
                // Decode base64 embedding columns back to Buffer
                if (col === "embedding" && typeof val === "string" && val.length > 0) {
                  return Buffer.from(val, "base64");
                }
                if (val === null || val === undefined) return null;
                return val;
              });
              stmt.run(...values);
            }
          });

          insertMany(rows);

          // FTS is kept in sync by triggers on the content tables.
          // INSERT OR REPLACE fires DELETE then INSERT triggers, which update FTS automatically.

          log(`Sync: ${rows.length} rows → ${table}`);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ applied: rows.length, table }));
        } catch (err) {
          log(`Sync error: ${err.message}`);
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: err.message }));
        }
      });
      return;
    }

    res.writeHead(404);
    res.end();
  });

  const wss = new WebSocketServer({
    server: httpServer,
    path: "/ws",
    verifyClient: ({ req }, done) => {
      if (!verifyAuth(req)) {
        log("Rejected connection: invalid token");
        done(false, 401, "Unauthorized");
        return;
      }
      done(true);
    },
  });

  wss.on("connection", (ws) => {
    log("Client connected");
    let activeAbort = null;

    const send = (msg) => {
      if (ws.readyState === ws.OPEN) {
        ws.send(JSON.stringify(msg));
      }
    };

    ws.on("message", async (data) => {
      let msg;
      try {
        msg = JSON.parse(data.toString());
      } catch {
        send({ type: "error", message: "Invalid JSON" });
        return;
      }

      switch (msg.type) {
        case "query": {
          // Cancel any prior query
          if (activeAbort) {
            activeAbort.abort();
            activeAbort = null;
          }

          const abortController = new AbortController();
          activeAbort = abortController;

          log(`Query: ${msg.prompt?.slice(0, 100)}`);

          try {
            const result = await handleQuery({
              prompt: msg.prompt,
              systemPrompt: msg.systemPrompt,
              cwd: msg.cwd,
              send,
              abortController,
            });

            if (!abortController.signal.aborted) {
              send({ type: "result", text: result.text, sessionId: result.sessionId, costUsd: result.costUsd });
            }
          } catch (err) {
            if (!abortController.signal.aborted) {
              log(`Query error: ${err.message}`);
              send({ type: "error", message: err.message });
            }
          } finally {
            if (activeAbort === abortController) {
              activeAbort = null;
            }
          }
          break;
        }

        case "stop":
          log("Stop requested");
          if (activeAbort) {
            activeAbort.abort();
            activeAbort = null;
          }
          break;

        default:
          send({ type: "error", message: `Unknown message type: ${msg.type}` });
      }
    });

    ws.on("close", () => {
      log("Client disconnected");
      if (activeAbort) {
        activeAbort.abort();
        activeAbort = null;
      }
    });

    ws.on("error", (err) => {
      log(`WebSocket error: ${err.message}`);
    });

    // Signal readiness
    send({ type: "init", sessionId: "" });
  });

  httpServer.listen(PORT, () => {
    log(`Listening on port ${PORT}`);
    log(`WebSocket: ws://0.0.0.0:${PORT}/ws`);
    log(`Health check: http://0.0.0.0:${PORT}/health`);
    log(`Upload: POST http://0.0.0.0:${PORT}/upload`);
    log(`Sync:   POST http://0.0.0.0:${PORT}/sync`);
  });
}

// --- Main ---

const args = process.argv.slice(2);

if (args[0] === "--serve") {
  startServer();
} else if (args.length > 0) {
  // CLI mode
  await runCli(args.join(" "));
} else {
  console.log("Usage:");
  console.log('  node agent.mjs "What did I do today?"     # CLI mode');
  console.log("  node agent.mjs --serve                     # WebSocket server mode");
  console.log("");
  console.log("Environment variables:");
  console.log("  DB_PATH       Path to omi.db (default: ~/omi-agent/data/omi.db)");
  console.log("  GEMINI_API_KEY  For semantic search embeddings");
  console.log("  AUTH_TOKEN    Required for server mode (bearer token for WebSocket auth)");
  console.log("  PORT          Server port (default: 8080)");
  process.exit(0);
}
