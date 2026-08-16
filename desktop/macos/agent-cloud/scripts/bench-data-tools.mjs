// E6: data-tool latency at churned-user scale. Times every query shape the
// agent actually issues, against the (inflated) DB. Deterministic queries.
import { createRequire } from "module";
const require = createRequire(new URL("../package.json", import.meta.url));
const Database = require("better-sqlite3");
const dt = await import(new URL("../data-tools.mjs", import.meta.url));

const db = new Database(process.argv[2], { readonly: false });
db.pragma("journal_mode = WAL");

const N = db.prepare("SELECT COUNT(*) n FROM screenshots").get().n;
console.log(`rows=${N}`);

function bench(name, fn, reps = 5) {
  fn(); // warm
  const times = [];
  for (let i = 0; i < reps; i++) {
    const t0 = process.hrtime.bigint();
    fn();
    times.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  times.sort((a, b) => a - b);
  console.log(`${name.padEnd(38)} p50=${times[Math.floor(reps / 2)].toFixed(1)}ms max=${times[reps - 1].toFixed(1)}ms`);
  return times[Math.floor(reps / 2)];
}

// Ranges the tools/researcher actually use.
const day = dt.resolveRange({ days_ago: 1 });
const week = dt.resolveRange({ days_ago: 7 });
const month = dt.resolveRange({ days_ago: 30 });

bench("activityCounts (1 day)", () => dt.activityCounts(db, day));
bench("activityCounts (30 days)", () => dt.activityCounts(db, month));
bench("appUsageMatrix (7 days)", () => dt.appUsageMatrix(db, week));
bench("appUsageMatrix (30 days)", () => dt.appUsageMatrix(db, month));
bench("hourlyTimeline (1 day)", () => dt.hourlyTimeline(db, day));
bench("topWindows (7 days)", () => dt.topWindows(db, week));

// FTS keyword search (researcher content-recall path)
bench("FTS MATCH single term", () =>
  db.prepare("SELECT s.timestamp, s.appName, s.windowTitle FROM screenshots_fts f JOIN screenshots s ON s.id=f.rowid WHERE screenshots_fts MATCH ? LIMIT 200").all("deadline"),
);
bench("FTS MATCH phrase+recent", () =>
  db.prepare("SELECT s.timestamp, s.appName FROM screenshots_fts f JOIN screenshots s ON s.id=f.rowid WHERE screenshots_fts MATCH ? AND s.timestamp >= ? LIMIT 200").all("sprint review", week.start),
);

// Typical hand-rolled researcher SQL shapes
bench("GROUP BY app over 7d", () =>
  db.prepare("SELECT appName, COUNT(*) c FROM screenshots WHERE timestamp >= ? AND timestamp < ? GROUP BY appName ORDER BY c DESC").all(week.start, week.endExclusive),
);
bench("date() wrapped WHERE (anti-pattern)", () =>
  db.prepare("SELECT COUNT(*) FROM screenshots WHERE date(timestamp) = ?").get(week.start),
);
bench("task dedup COUNT DISTINCT", () =>
  db.prepare("SELECT COUNT(DISTINCT description) FROM action_items WHERE deleted = 0").get(),
);
bench("full recap assembly (7 days)", () => {
  const counts = dt.activityCounts(db, week);
  dt.emptyRangeStatement(week, counts) ??
    dt.formatAppUsage(week, dt.appUsageMatrix(db, week)) +
      dt.formatHourlyTimeline(dt.hourlyTimeline(db, week)) +
      dt.formatTopWindows(dt.topWindows(db, week));
});

console.log("\nquery plans (index usage):");
for (const [label, sql, args] of [
  ["range scan", "SELECT COUNT(*) FROM screenshots WHERE timestamp >= ? AND timestamp < ?", [week.start, week.endExclusive]],
  ["date() scan", "SELECT COUNT(*) FROM screenshots WHERE date(timestamp) = ?", [week.start]],
]) {
  const plan = db.prepare(`EXPLAIN QUERY PLAN ${sql}`).all(...args).map((r) => r.detail).join(" | ");
  console.log(`  ${label}: ${plan}`);
}
