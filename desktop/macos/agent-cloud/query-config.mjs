// Shared query() option pieces for agent.mjs — extracted so subagent
// definitions and the tool surface are unit-testable (agent.mjs itself is a
// long-running entrypoint with no exports).

// "Task" is required for the main agent to invoke declared subagents.
export const ALLOWED_TOOLS = [
  "Read",
  "Write",
  "Edit",
  "Bash",
  "Glob",
  "Grep",
  "WebSearch",
  "WebFetch",
  "Task",
];

// Fully-qualified MCP tool names as the SDK sees them (server "omi-tools").
export const RESEARCHER_TOOLS = [
  "mcp__omi-tools__execute_sql",
  "mcp__omi-tools__semantic_search",
  "mcp__omi-tools__get_daily_recap",
];

export function buildAgentDefinitions(schemaText) {
  return {
    researcher: {
      // Routing note (measured, 2026-07-21 real-data runs): delegation costs one
      // extra hop (~20s), which pays off only on row-heavy work. Route tasks that
      // must read MANY rows (task triage, content recall/FTS over screenshots,
      // multi-day pattern analysis); answer directly when one or two aggregate
      // queries suffice.
      description:
        "Data exploration specialist for the user's OMI database. Use for ROW-HEAVY work: " +
        "searching or reading through many screenshots/tasks/transcripts (content recall, " +
        "task triage, multi-day pattern analysis across tables). It returns distilled " +
        "findings, keeping raw rows out of the main conversation. Do NOT use it for quick " +
        "lookups or questions one aggregate query can answer.",
      prompt: `You are a research analyst exploring the user's OMI desktop database.

DATABASE SCHEMA:
${schemaText}

Your job: run the queries needed to answer the objective, then return distilled findings.
- Use execute_sql for structured queries (auto-limited to 200 rows; FTS5 MATCH available).
- Use semantic_search for fuzzy/conceptual recall over screenshot OCR text.
- Use get_daily_recap for activity summaries. ONE call covers any date range — never
  call it once per day.
- NEVER paste raw query results into your answer. Aggregate, rank, and summarize with
  concrete evidence (counts, time ranges, top items).
- Your final message is consumed by another agent: findings only, no preamble.`,
      tools: RESEARCHER_TOOLS,
      // Haiku measured fastest and ~3x cheaper than inherited Opus with equal-or-better
      // accuracy on real data; keep its prompt simple — small models ignore meta-instructions.
      model: "haiku",
    },
  };
}
