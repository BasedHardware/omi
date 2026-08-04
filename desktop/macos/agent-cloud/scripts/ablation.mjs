// Ablation experiment: push the cloud agent cheaper/faster/more-accurate by
// cutting knobs one at a time until accuracy breaks, then report the frontier.
// Each variant is the base agent with env knobs flipped (see agent.mjs
// mainModel/allowedToolsFor/agentsFor/selectSystemPrompt/mcpServersFor).
//
// Usage: node scripts/ablation.mjs <db_path> [variant1 variant2 ...]
// Ground truth is derived from the DB itself so it stays honest across machines.

import { createRequire } from "module";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../package.json"));
const Database = require("better-sqlite3");

const DB = process.argv[2];
if (!DB) throw new Error("usage: node scripts/ablation.mjs <db_path> [variants...]");

// --- Ground truth from the DB (so a right answer is machine-checkable) ---
const db = new Database(DB, { readonly: true });
const openTasks = db.prepare("SELECT COUNT(*) n FROM action_items WHERE completed = 0").get().n;
const totalTasks = db.prepare("SELECT COUNT(*) n FROM action_items").get().n;
const completedTasks = db.prepare("SELECT COUNT(*) n FROM action_items WHERE completed = 1").get().n;
const completionPct = Math.round((completedTasks / Math.max(1, totalTasks)) * 100);
const topAppAll = db.prepare("SELECT appName FROM screenshots GROUP BY appName ORDER BY COUNT(*) DESC LIMIT 1").get()?.appName;
const topAppWeek = db
  .prepare(
    "SELECT appName FROM screenshots WHERE timestamp >= datetime('now','-7 days') GROUP BY appName ORDER BY COUNT(*) DESC LIMIT 1",
  )
  .get()?.appName;
const memoryCount = db.prepare("SELECT COUNT(*) n FROM memories").get().n;
// FTS may be absent in a trimmed DB; fall back to a LIKE scan so ground-truth
// computation never crashes the sweep.
const safeGet = (sql, dflt) => {
  try {
    return db.prepare(sql).get().n;
  } catch {
    return dflt;
  }
};
const deadlineHits =
  safeGet("SELECT COUNT(*) n FROM screenshots WHERE screenshots_fts MATCH 'deadline'", null) ??
  safeGet("SELECT COUNT(*) n FROM screenshots WHERE lower(ocrText) LIKE '%deadline%'", 0);
db.close();

// Battery grounded in the REAL omi tool/feature mix (PostHog project 302298,
// 30d): the 5 highest-reach data tools users actually invoke — search_memories
// (597 users, widest), Action Items (8996 users, #1 feature), get_daily_recap,
// get_app_usage, semantic_search — plus 2 EXPERIMENTAL hard cases: a row-heavy
// analysis that should delegate to the researcher, and the absent-data honesty
// case (the report's 10-tool-call "no data" waste). Each prompt is phrased the
// way a real user would ask, not as SQL.
const BATTERY = [
  {
    id: "memory_recall", // search_memories — #1 tool by user reach
    prompt: "What do you remember about me — my preferences and personal facts?",
    check: (t) => {
      const l = t.toLowerCase();
      return ["dark mode", "shellfish", "menzel", "async", "bedtime"].filter((f) => l.includes(f)).length >= 2;
    },
    truth: `${memoryCount} memories seeded`,
  },
  {
    id: "open_tasks", // Action Items — #1 feature by user reach
    prompt: "How many things do I still have on my to-do list?",
    check: (t) => new RegExp(`\\b${openTasks}\\b`).test(t),
    truth: `${openTasks} open`,
  },
  {
    id: "yesterday_recap", // get_daily_recap
    prompt: "What did I get done yesterday?",
    check: (t) => t.trim().length > 40 && !/error|couldn't|unable/i.test(t), // coherent recap, not a failure
    truth: "coherent recap",
  },
  {
    id: "top_app_week", // get_app_usage
    prompt: "What have I been spending the most screen time on this past week?",
    check: (t) => topAppWeek && t.toLowerCase().includes(topAppWeek.toLowerCase()),
    truth: topAppWeek,
  },
  // --- experimental: harder, push the agent ---
  {
    id: "productivity_analysis", // row-heavy → should delegate to researcher
    prompt:
      "Analyze my productivity this month: what's my task completion rate, and which app do I use most? Give the completion rate as a percentage.",
    check: (t) => /\d+\s?%/.test(t) && topAppAll && t.toLowerCase().includes(topAppAll.toLowerCase()),
    truth: `~${completionPct}% complete, top ${topAppAll}`,
  },
  {
    id: "absent_data_honesty", // the report's "no data → 10 verification calls" case
    prompt: "What did I do on January 1st, 2020?",
    check: (t) => /\bno\b|not any|nothing|don't have|no (activity|data|record)/i.test(t) && !/xcode|safari|slack|chrome/i.test(t),
    truth: "must say no data, not fabricate",
  },
];

// Variants: name -> env overrides. "base" is the shipped config.
const VARIANTS = {
  base: {},
  no_browser: { OMI_NO_PLAYWRIGHT: "1" },
  min_tools: { OMI_NO_PLAYWRIGHT: "1", OMI_MINIMAL_TOOLS: "1" },
  min_prompt: { OMI_NO_PLAYWRIGHT: "1", OMI_MINIMAL_TOOLS: "1", OMI_MINIMAL_PROMPT: "1" },
  sonnet: { OMI_NO_PLAYWRIGHT: "1", OMI_MINIMAL_TOOLS: "1", OMI_MINIMAL_PROMPT: "1", OMI_MAIN_MODEL: "claude-sonnet-4-6" },
  haiku: { OMI_NO_PLAYWRIGHT: "1", OMI_MINIMAL_TOOLS: "1", OMI_MINIMAL_PROMPT: "1", OMI_MAIN_MODEL: "claude-haiku-4-5-20251001" },
  haiku_nosub: {
    OMI_NO_PLAYWRIGHT: "1", OMI_MINIMAL_TOOLS: "1", OMI_MINIMAL_PROMPT: "1",
    OMI_MAIN_MODEL: "claude-haiku-4-5-20251001", OMI_NO_SUBAGENT: "1",
  },
};

const selected = process.argv.slice(3);
const variantNames = selected.length ? selected : Object.keys(VARIANTS);

function runOne(prompt, env) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [join(here, "../agent.mjs"), prompt], {
      env: { ...process.env, DB_PATH: DB, ...env, CLAUDECODE: "", CLAUDE_CODE_ENTRYPOINT: "" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const t0 = Date.now();
    child.on("close", () => {
      const wallS = (Date.now() - t0) / 1000;
      const tools = (out.match(/\[Tool started/g) || []).length;
      const costM = out.match(/cost: \$([0-9.]+)/);
      const cost = costM ? parseFloat(costM[1]) : NaN;
      const answer = out
        .split("=".repeat(60))
        .pop()
        .replace(/\[(Tool|Subagent|Session|Error|Done)[^\]]*\]/g, "")
        .trim();
      resolve({ wallS, tools, cost, answer });
    });
  });
}

const results = [];
for (const name of variantNames) {
  const env = VARIANTS[name];
  if (!env) {
    console.log(`skip unknown variant: ${name}`);
    continue;
  }
  for (const task of BATTERY) {
    const r = await runOne(task.prompt, env);
    const correct = !!r.answer && task.check(r.answer);
    results.push({ variant: name, task: task.id, ...r, correct });
    console.log(
      `${name.padEnd(12)} ${task.id.padEnd(20)} wall=${r.wallS.toFixed(1)}s tools=${r.tools} ` +
        `cost=$${Number.isNaN(r.cost) ? "?" : r.cost.toFixed(4)} correct=${correct ? "✓" : "✗"} (truth=${task.truth})`,
    );
    if (!correct) console.log(`    ↳ got: ${r.answer.replace(/\s+/g, " ").slice(0, 200)}`);
  }
}

// --- Per-variant rollup ---
console.log("\n=== ROLLUP (variant: accuracy | median wall | total cost | avg tools) ===");
for (const name of variantNames) {
  const rows = results.filter((r) => r.variant === name);
  if (!rows.length) continue;
  const acc = rows.filter((r) => r.correct).length;
  const walls = rows.map((r) => r.wallS).sort((a, b) => a - b);
  const medWall = walls[Math.floor(walls.length / 2)];
  const totCost = rows.reduce((s, r) => s + (Number.isNaN(r.cost) ? 0 : r.cost), 0);
  const avgTools = rows.reduce((s, r) => s + r.tools, 0) / rows.length;
  console.log(
    `${name.padEnd(12)} acc=${acc}/${rows.length}  medWall=${medWall.toFixed(1)}s  ` +
      `cost=$${totCost.toFixed(4)}  avgTools=${avgTools.toFixed(1)}`,
  );
}
