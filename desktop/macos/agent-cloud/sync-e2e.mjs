#!/usr/bin/env node
// End-to-end regression test for the /sync endpoint's per-row column handling.
//
// Runs the real agent.mjs server against a real SQLite file and POSTs a batch
// shaped exactly like AgentSyncService's payload (NULL columns omitted per row).
// Before the column-set grouping fix, the batch schema came from rows[0], so a
// first row that was not yet OCR'd stripped ocrText/embedding from every other
// row in the batch while /sync still reported success.
//
// Run: npm test   (from desktop/macos/agent-cloud)

import Database from "better-sqlite3";
import { spawn } from "child_process";
import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 8791;
const TOKEN = "sync-e2e-token";

const workDir = mkdtempSync(join(tmpdir(), "omi-agent-sync-e2e-"));
const dbPath = join(workDir, "omi.db");

const failures = [];
function check(condition, message) {
  if (!condition) failures.push(message);
}

function seedDatabase() {
  const db = new Database(dbPath);
  db.exec(`CREATE TABLE screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    appName TEXT NOT NULL,
    windowTitle TEXT,
    imagePath TEXT NOT NULL DEFAULT '',
    ocrText TEXT,
    isIndexed INTEGER NOT NULL DEFAULT 0,
    embedding BLOB
  )`);
  // The VM always opens a database uploaded from the desktop, which already has
  // screenshots. Seed one so the fixture matches that shape.
  db.prepare(
    "INSERT INTO screenshots (id, timestamp, appName, imagePath, ocrText) VALUES (100, ?, ?, ?, ?)"
  ).run("2026-07-20 09:00:00", "Finder", "/seed.png", "seed row");
  db.close();
}

async function startServer() {
  const child = spawn(process.execPath, [join(__dirname, "agent.mjs"), "--serve"], {
    env: { ...process.env, DB_PATH: dbPath, AUTH_TOKEN: TOKEN, PORT: String(PORT) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const logs = [];
  child.stdout.on("data", (d) => logs.push(d.toString()));
  child.stderr.on("data", (d) => logs.push(d.toString()));

  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const resp = await fetch(`http://127.0.0.1:${PORT}/health`);
      if (resp.ok) return { child, logs };
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  child.kill();
  throw new Error(`server did not become healthy:\n${logs.join("")}`);
}

function sync(rows) {
  return fetch(`http://127.0.0.1:${PORT}/sync`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ table: "screenshots", rows }),
  }).then((r) => r.json());
}

let server;
try {
  seedDatabase();
  server = await startServer();

  const embedding = Buffer.alloc(12, 7).toString("base64");

  // Row 1 is captured but not yet OCR'd or embedded; rows 2 and 3 are populated.
  const applied = await sync([
    { id: 1, timestamp: "2026-07-25 10:00:00", appName: "Chrome", imagePath: "/a.png", isIndexed: 0 },
    { id: 2, timestamp: "2026-07-25 10:00:05", appName: "Chrome", imagePath: "/b.png", isIndexed: 1, ocrText: "quarterly revenue plan", embedding },
    { id: 3, timestamp: "2026-07-25 10:00:10", appName: "Slack", imagePath: "/c.png", isIndexed: 1, ocrText: "ship the sync fix", windowTitle: "#eng" },
  ]);
  check(applied.applied === 3, `expected applied=3, got ${JSON.stringify(applied)}`);

  // Reverse order: the populated row first, a bare row after.
  await sync([
    { id: 4, timestamp: "2026-07-25 11:00:00", appName: "Chrome", imagePath: "/d.png", isIndexed: 1, ocrText: "row four text" },
    { id: 5, timestamp: "2026-07-25 11:00:05", appName: "Chrome", imagePath: "/e.png", isIndexed: 0 },
  ]);

  const db = new Database(dbPath, { readonly: true });
  const row = (id) => db.prepare("SELECT * FROM screenshots WHERE id = ?").get(id);

  const two = row(2);
  check(two.ocrText === "quarterly revenue plan", `row 2 ocrText: ${JSON.stringify(two.ocrText)}`);
  check(two.embedding?.length === 12, `row 2 embedding: ${two.embedding?.length}`);

  const three = row(3);
  check(three.ocrText === "ship the sync fix", `row 3 ocrText: ${JSON.stringify(three.ocrText)}`);
  check(three.windowTitle === "#eng", `row 3 windowTitle: ${JSON.stringify(three.windowTitle)}`);

  // A row that omits a column must not inherit the previous row's value, and the
  // previous row must keep its own.
  check(row(4).ocrText === "row four text", `row 4 ocrText: ${JSON.stringify(row(4).ocrText)}`);
  check(row(5).ocrText === null, `row 5 ocrText: ${JSON.stringify(row(5).ocrText)}`);

  // The pre-existing row is untouched by an unrelated batch.
  check(row(100).ocrText === "seed row", `row 100 ocrText: ${JSON.stringify(row(100).ocrText)}`);
  db.close();
} finally {
  server?.child.kill();
  rmSync(workDir, { recursive: true, force: true });
}

if (failures.length > 0) {
  console.error("FAIL: /sync dropped columns the desktop sent");
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log("PASS: /sync writes each row with its own column set");
