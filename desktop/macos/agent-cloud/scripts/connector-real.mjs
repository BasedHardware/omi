// REAL connector / external-environment test — no mocks.
//
// Points the real cloud agent at LIVE api.omi.me with a real signed-in user's
// Firebase token, so it discovers and calls the user's ACTUAL connectors
// (calendar, gmail, health, web search…). Read-only queries only — never sends
// mail or mutates a calendar. For each query it reports: connectors registered,
// which connector tools the agent actually called, wall/cost, and the real
// answer (for the human to verify against their real accounts — only they know
// the ground truth).
//
// Usage: OMI_FIREBASE_TOKEN=<real-idToken> node scripts/connector-real.mjs <db_path> [model]

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const DB = process.argv[2];
const MODEL = process.argv[3] || "claude-sonnet-4-6";
const TOKEN = process.env.OMI_FIREBASE_TOKEN;
if (!DB || !TOKEN) throw new Error("usage: OMI_FIREBASE_TOKEN=<idToken> node scripts/connector-real.mjs <db> [model]");

// Read-only, side-effect-free queries over the real connected surface
// (calendar, gmail, files, health, web). Never creates/updates/deletes.
const BATTERY = [
  { id: "calendar", prompt: "What's on my calendar this week? List the events." },
  { id: "gmail", prompt: "What are my most recent Gmail messages about? Summarize the latest few." },
  { id: "files", prompt: "Search my connected files for anything about 'omi' or 'agent' and tell me what you find." },
  { id: "health", prompt: "How has my sleep been recently, according to my health data?" },
  { id: "web", prompt: "Fetch https://example.com and tell me the heading on the page." },
  {
    id: "cross_connector",
    prompt: "Based on my calendar this week and my most recent emails, is there anything I should prepare for?",
  },
];

function run(prompt) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [join(here, "../agent.mjs"), prompt], {
      env: {
        ...process.env,
        DB_PATH: DB,
        OMI_FIREBASE_TOKEN: TOKEN,
        OMI_MAIN_MODEL: MODEL,
        // BACKEND_URL left default → real https://api.omi.me
        CLAUDECODE: "",
        CLAUDE_CODE_ENTRYPOINT: "",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    const t0 = Date.now();
    child.on("close", () => {
      const wallS = (Date.now() - t0) / 1000;
      const reg = /Registered (\d+) backend tools/.exec(out);
      const fetched = /Fetched (\d+) tools from Python backend/.exec(out);
      const toolLines = [...out.matchAll(/\[Tool started: ([^\]]+)\]/g)].map((m) => m[1]);
      const errLine = /\[backend-tools\][^\n]*(Failed|Error)[^\n]*/.exec(out);
      const answer = out.split("=".repeat(60)).pop().replace(/\[(Tool|Subagent|Session|Error|Done)[^\]]*\]/g, "").trim();
      const cost = /cost: \$([0-9.]+)/.exec(out);
      resolve({
        wallS,
        registered: reg ? Number(reg[1]) : 0,
        fetched: fetched ? Number(fetched[1]) : 0,
        backendErr: errLine ? errLine[0] : null,
        tools: toolLines,
        cost: cost ? parseFloat(cost[1]) : NaN,
        answer,
      });
    });
  });
}

console.log(`REAL connector test — model=${MODEL}, backend=api.omi.me (live)\n`);
for (const task of BATTERY) {
  const r = await run(task.prompt);
  if (r.backendErr) {
    console.log(`${task.id}: BACKEND FETCH PROBLEM → ${r.backendErr}`);
    break; // token invalid/expired or endpoint down — stop, don't spam
  }
  console.log(
    `\n### ${task.id}  (registered ${r.registered} connectors, ${r.wallS.toFixed(1)}s, $${Number.isNaN(r.cost) ? "?" : r.cost.toFixed(4)})`,
  );
  console.log(`  connectors called: ${r.tools.filter((t) => !t.startsWith("subagent")).join(", ") || "— none —"}`);
  console.log(`  answer: ${r.answer.replace(/\s+/g, " ").slice(0, 400)}`);
}
console.log("\n(verify answers against your real calendar/inbox — only you know the ground truth)");
