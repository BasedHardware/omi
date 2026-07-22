// Data-shaping helpers for the omi-tools MCP tools. Pure functions over a
// better-sqlite3 handle so tool output shapes are unit-testable.
//
// Eval-battery findings these shapes fix (2026-07-22, real-data runs):
// - get_daily_recap could only anchor to "now" (days_ago), so date-specific
//   questions fell back to 13+ hand-rolled SQL turns → explicit date ranges.
// - An empty-ish recap triggered 7 verification queries → the empty case is
//   now a single authoritative statement the model can trust.
// - Day-vs-app breakdowns were hand-rolled with 14-16 GROUP BY turns →
//   appUsageMatrix returns the whole matrix in one call.

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function resolveRange({ days_ago, start_date, end_date } = {}) {
  if (start_date !== undefined || end_date !== undefined) {
    if (!DATE_RE.test(start_date ?? "") || !DATE_RE.test(end_date ?? start_date ?? "")) {
      throw new Error("start_date/end_date must be YYYY-MM-DD");
    }
    const end = end_date ?? start_date;
    if (end < start_date) throw new Error("end_date must not precede start_date");
    const endExclusive = nextDay(end);
    const label = start_date === end ? start_date : `${start_date} to ${end}`;
    return { start: start_date, endExclusive, label, spanDays: spanDays(start_date, endExclusive) };
  }
  const n = Math.max(0, Math.floor(days_ago ?? 1));
  const now = new Date();
  const today = isoDate(now);
  const start = isoDate(new Date(now.getTime() - n * 86400000));
  const endExclusive = n === 0 ? nextDay(today) : today;
  const label = n === 0 ? "Today" : n === 1 ? "Yesterday" : `Past ${n} days`;
  return { start, endExclusive, label, spanDays: Math.max(1, n) };
}

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function nextDay(date) {
  const d = new Date(`${date}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return isoDate(d);
}
function spanDays(start, endExclusive) {
  return Math.max(1, Math.round((new Date(`${endExclusive}T00:00`) - new Date(`${start}T00:00`)) / 86400000));
}

export function activityCounts(db, range) {
  const one = (sql) => db.prepare(sql).get(range.start, range.endExclusive).n;
  return {
    screenshots: one("SELECT COUNT(*) n FROM screenshots WHERE timestamp >= ? AND timestamp < ?"),
    sessions: one(
      "SELECT COUNT(*) n FROM transcription_sessions WHERE startedAt >= ? AND startedAt < ? AND deleted = 0 AND discarded = 0",
    ),
    tasksCreated: one("SELECT COUNT(*) n FROM action_items WHERE createdAt >= ? AND createdAt < ? AND deleted = 0"),
  };
}

export function emptyRangeStatement(range, counts) {
  if (counts.screenshots > 0 || counts.sessions > 0 || counts.tasksCreated > 0) return null;
  return (
    `# ${range.label}: no activity recorded\n\n` +
    `Authoritative: 0 screenshots, 0 conversations, and 0 tasks were recorded between ` +
    `${range.start} and ${range.endExclusive} (exclusive). There is no data to analyze for this ` +
    `range — do not run further queries to verify.`
  );
}

export function appUsageMatrix(db, range) {
  const rows = db
    .prepare(
      `SELECT date(timestamp) AS day, appName, COUNT(*) AS captures
       FROM screenshots
       WHERE timestamp >= ? AND timestamp < ? AND appName IS NOT NULL AND appName != ''
       GROUP BY day, appName ORDER BY day ASC, captures DESC`,
    )
    .all(range.start, range.endExclusive);
  const totals = new Map();
  const days = new Map();
  for (const r of rows) {
    totals.set(r.appName, (totals.get(r.appName) ?? 0) + r.captures);
    if (!days.has(r.day)) days.set(r.day, []);
    days.get(r.day).push({ appName: r.appName, captures: r.captures });
  }
  return {
    days: [...days.entries()].map(([day, apps]) => ({ day, apps })),
    totals: [...totals.entries()].map(([appName, captures]) => ({ appName, captures })).sort((a, b) => b.captures - a.captures),
  };
}

export function formatAppUsage(range, matrix) {
  if (matrix.totals.length === 0) {
    return `# App usage ${range.label}\n\nAuthoritative: no screen activity recorded in this range.`;
  }
  let out = `# App usage ${range.label}\n\n## Totals (~10s per capture)\n`;
  for (const t of matrix.totals.slice(0, 15)) {
    out += `- **${t.appName}**: ${t.captures} captures (~${Math.round((t.captures * 10) / 60)} min)\n`;
  }
  out += `\n## Per day\n`;
  for (const d of matrix.days) {
    const top = d.apps
      .slice(0, 5)
      .map((a) => `${a.appName} ${a.captures}`)
      .join(", ");
    const dayTotal = d.apps.reduce((s, a) => s + a.captures, 0);
    out += `- **${d.day}** (${dayTotal} captures): ${top}\n`;
  }
  return out;
}

export function hourlyTimeline(db, range) {
  return db
    .prepare(
      `SELECT strftime('%H', timestamp) AS hour, appName, COUNT(*) AS captures
       FROM screenshots
       WHERE timestamp >= ? AND timestamp < ? AND appName IS NOT NULL AND appName != ''
       GROUP BY hour, appName ORDER BY hour ASC, captures DESC`,
    )
    .all(range.start, range.endExclusive);
}

export function formatHourlyTimeline(rows) {
  if (rows.length === 0) return "";
  const byHour = new Map();
  for (const r of rows) if (!byHour.has(r.hour)) byHour.set(r.hour, r); // first = top app of hour
  let out = `\n## Hourly timeline (top app per hour)\n`;
  for (const [hour, r] of byHour) {
    out += `- ${hour}:00 — ${r.appName} (${r.captures} captures)\n`;
  }
  return out;
}

export function topWindows(db, range, appLimit = 3, windowLimit = 4) {
  const topApps = db
    .prepare(
      `SELECT appName FROM screenshots
       WHERE timestamp >= ? AND timestamp < ? AND appName IS NOT NULL AND appName != ''
       GROUP BY appName ORDER BY COUNT(*) DESC LIMIT ?`,
    )
    .all(range.start, range.endExclusive, appLimit);
  const stmt = db.prepare(
    `SELECT windowTitle, COUNT(*) AS captures FROM screenshots
     WHERE timestamp >= ? AND timestamp < ? AND appName = ? AND windowTitle IS NOT NULL AND windowTitle != ''
     GROUP BY windowTitle ORDER BY captures DESC LIMIT ?`,
  );
  return topApps.map((a) => ({
    appName: a.appName,
    windows: stmt.all(range.start, range.endExclusive, a.appName, windowLimit),
  }));
}

export function formatTopWindows(perApp) {
  const withWindows = perApp.filter((a) => a.windows.length > 0);
  if (withWindows.length === 0) return "";
  let out = `\n## What was on screen (top windows)\n`;
  for (const a of withWindows) {
    out += `- **${a.appName}**: ${a.windows.map((w) => `${w.windowTitle} (${w.captures})`).join("; ")}\n`;
  }
  return out;
}

// E7 batch shape: run several independent read queries in ONE tool call.
// The latency win is eliminating model round-trips (2-6s each), not SQL time
// (E6: worst single query 126ms at 600K rows) — so execution stays serial.
// Errors are isolated per query: one bad statement never voids the batch.
export function runSqlBatch(runOne, queries) {
  const parts = queries.map((sql, i) => {
    const head = sql.replace(/\s+/g, " ").trim().slice(0, 80);
    let body;
    try {
      body = runOne(sql);
    } catch (e) {
      body = JSON.stringify({ error: e?.message || String(e) });
    }
    return `-- [${i + 1}] ${head}\n${body}`;
  });
  return parts.join("\n\n");
}
