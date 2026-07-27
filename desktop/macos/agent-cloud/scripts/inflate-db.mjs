// E6 scale-inflation: grow the test DB to churned-user scale (600K screenshots).
// Deterministic (seeded PRNG) so the experiment is reproducible.
import { createRequire } from "module";
const require = createRequire(new URL("../package.json", import.meta.url));
const Database = require("better-sqlite3");

const DB = process.argv[2];
const TARGET = parseInt(process.argv[3] || "600000", 10);
if (!DB) throw new Error("usage: node inflate-db.mjs <db> [target]");

let seed = 42;
const rand = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
const pick = (a) => a[Math.floor(rand() * a.length)];

const APPS = ["Xcode", "Safari", "Slack", "Chrome", "Terminal", "Notion", "Figma", "Mail", "Zoom", "Finder", "Spotify", "Notes"];
const WORDS = ("meeting notes proposal deadline review sprint deploy release invoice budget design draft agenda " +
  "roadmap standup client feedback migration database schema latency benchmark experiment churn retention " +
  "onboarding checkout payment subscription analytics dashboard funnel cohort metric alert incident rollback").split(" ");
const sentence = (n) => Array.from({ length: n }, () => pick(WORDS)).join(" ");

const db = new Database(DB);
db.pragma("journal_mode = WAL");
db.pragma("synchronous = OFF");

const existing = db.prepare("SELECT COUNT(*) n FROM screenshots").get().n;
const need = TARGET - existing;
console.log(`existing=${existing} target=${TARGET} inserting=${need}`);
if (need > 0) {
  const ins = db.prepare(
    "INSERT INTO screenshots (timestamp, appName, windowTitle, imagePath, ocrText) VALUES (?, ?, ?, ?, ?)"
  );
  const now = Date.now();
  const DAY = 86400000;
  const insertMany = db.transaction((rows) => { for (const r of rows) ins.run(...r); });
  let batch = [];
  for (let i = 0; i < need; i++) {
    const daysBack = Math.floor(rand() * 180);
    const hour = 8 + Math.floor(rand() * 12);
    const t = new Date(now - daysBack * DAY);
    t.setHours(hour, Math.floor(rand() * 60), Math.floor(rand() * 60), 0);
    const ts = t.toISOString().replace("T", " ").slice(0, 19);
    const app = pick(APPS);
    batch.push([ts, app, `${app} — ${sentence(3)}`, `/tmp/s${i}.png`, sentence(24)]);
    if (batch.length === 5000) { insertMany(batch); batch = []; if (i % 100000 < 5000) console.log(`...${i}`); }
  }
  if (batch.length) insertMany(batch);
}

console.log("rebuilding FTS...");
db.exec("INSERT INTO screenshots_fts(screenshots_fts) VALUES('rebuild')");

// Tasks with the measured near-duplicate pathology (~63% dupes).
const taskCount = db.prepare("SELECT COUNT(*) n FROM action_items").get().n;
if (taskCount < 3000) {
  const ins = db.prepare(
    "INSERT INTO action_items (description, completed, priority, category, createdAt, updatedAt) VALUES (?, ?, 'medium', 'work', ?, ?)"
  );
  const bases = Array.from({ length: 1100 }, () => `${pick(["Send", "Review", "Fix", "Update", "Schedule"])} ${sentence(4)}`);
  const tx = db.transaction(() => {
    for (let i = 0; i < 3000; i++) {
      const base = pick(bases); // ~63% collide onto reused bases
      const t = new Date(Date.now() - Math.floor(rand() * 90) * 86400000).toISOString().slice(0, 19).replace("T", " ");
      ins.run(rand() < 0.63 ? base : `${base} ${sentence(2)}`, rand() < 0.4 ? 1 : 0, t, t);
    }
  });
  tx();
}

db.pragma("synchronous = NORMAL");
db.exec("ANALYZE");
const final = db.prepare("SELECT COUNT(*) n FROM screenshots").get().n;
const fts = db.prepare("SELECT COUNT(*) n FROM screenshots_fts").get().n;
console.log(`done: screenshots=${final} fts=${fts} tasks=${db.prepare("SELECT COUNT(*) n FROM action_items").get().n}`);
