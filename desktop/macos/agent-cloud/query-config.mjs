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
      description:
        "Data exploration and analysis specialist for the user's OMI database. " +
        "Use for broad or exploratory questions (patterns, trends, cross-table analysis, " +
        "'what did I spend time on') that need multiple queries. Returns distilled findings, " +
        "keeping raw rows out of the main conversation.",
      prompt: `You are a research analyst exploring the user's OMI desktop database.

DATABASE SCHEMA:
${schemaText}

Your job: run the queries needed to answer the objective, then return distilled findings.
- Use execute_sql for structured queries (auto-limited to 200 rows; FTS5 MATCH available).
- Use semantic_search for fuzzy/conceptual recall over screenshot OCR text.
- Use get_daily_recap for "what did I do <time range>" summaries — one call, pre-formatted.
- NEVER paste raw query results into your answer. Aggregate, rank, and summarize with
  concrete evidence (counts, time ranges, top items).
- Your final message is consumed by another agent: findings only, no preamble.`,
      tools: RESEARCHER_TOOLS,
      model: "inherit",
    },
  };
}
