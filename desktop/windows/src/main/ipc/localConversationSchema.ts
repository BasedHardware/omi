// Read indexes for `local_conversation`, kept in one importable constant so the
// query-plan test proves the SAME DDL that db.ts ships — the LIVE_NOTES_SCHEMA /
// INSIGHTS_SCHEMA discipline. A re-declared copy in the test could drift green
// while the shipped index was dropped (see the SQL-test-drift trap).
//
// The table itself is created in db.ts's bootstrap block; only the additive index
// lives here (created after the base table + additive columns exist). `created_at`
// is a base column present in every install, so the index is always creatable.
//
// Why: `listLocalConversations()` reads `... ORDER BY created_at DESC` on a table
// with no index beyond the PK and no pruning. Without this index that is a full
// scan + a temp-b-tree sort on every Conversations fetch; the index makes it an
// index-ordered scan (no sort).
export const LOCAL_CONVERSATION_SCHEMA = `
  CREATE INDEX IF NOT EXISTS idx_local_conversation_created_at
    ON local_conversation(created_at);
`
