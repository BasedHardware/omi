import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { afterEach, describe, expect, it } from "vitest";

import { buildContextSnapshot } from "../src/runtime/context-snapshot.js";
import { recordJournalExchange } from "../src/runtime/conversation-journal.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";

/**
 * The snapshot every chat turn waits on joins `conversation_turns` to
 * `conversation_turn_revisions` on `turn_id`. That table is keyed
 * `(conversation_id, turn_seq)`, so without an index carrying `turn_id` the join
 * degrades to walking every revision row of the conversation for every turn in
 * it. On a real account (7,263 turns) the query measured 27.65s against the 15s
 * `get_context_snapshot` budget, so every chat turn timed out before the model
 * was queried. With the index the same query measured 0.03s.
 *
 * These assert the plan and the migration rather than a wall-clock threshold: a
 * timing assertion on shared CI hardware is the flaky kind this suite deletes,
 * while the plan is the actual contract — an equality seek on both join keys.
 */

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

function newStateDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-context-snapshot-index-"));
  createdDirs.push(dir);
  return dir;
}

const OWNER = "owner";
const SURFACE = "main_chat";

function newFixture(): { store: SqliteAgentStore; sessionId: string; conversationId: string } {
  const store = new SqliteAgentStore({ stateDir: newStateDir(), reconcileOnOpen: false });
  const session = store.insertSession({ ownerId: OWNER, surfaceKind: SURFACE, defaultAdapterId: "acp" });
  const conversationId = "conv-context-snapshot-index";
  store.insertSurfaceConversation({
    ownerId: OWNER,
    surfaceKind: SURFACE,
    externalRefKind: "chat",
    externalRefId: "context-snapshot-index",
    conversationId,
    agentSessionId: session.sessionId,
    createdAtMs: 1,
    lastActiveAtMs: 1,
  });
  return { store, sessionId: session.sessionId, conversationId };
}

function seedExchanges(store: SqliteAgentStore, conversationId: string, count: number): void {
  for (let i = 0; i < count; i += 1) {
    recordJournalExchange(store, {
      ownerId: OWNER,
      conversationId,
      turns: [
        {
          role: "user",
          surfaceKind: SURFACE,
          origin: "local",
          status: "completed",
          content: `question ${i}`,
          contentBlocks: [],
          createdAtMs: 1_000 + i * 2,
        },
        {
          role: "assistant",
          surfaceKind: SURFACE,
          origin: "local",
          status: "completed",
          content: `answer ${i}`,
          contentBlocks: [],
          createdAtMs: 1_001 + i * 2,
        },
      ],
    });
  }
}

/** The join predicate the snapshot depends on, isolated so the plan is readable. */
const JOIN_PROBE_SQL = `
  SELECT ct.turn_id, COALESCE(MIN(revision.turn_seq), ct.turn_seq) AS insertion_seq
  FROM conversation_turns ct
  LEFT JOIN conversation_turn_revisions revision
    ON revision.conversation_id = ct.conversation_id
   AND revision.turn_id = ct.turn_id
  WHERE ct.conversation_id = ?
  GROUP BY ct.conversation_id, ct.turn_id
  ORDER BY ct.created_at_ms DESC, insertion_seq DESC
  LIMIT 40`;

describe("context snapshot turn-revision lookup", () => {
  it("seeks the revision join on both keys instead of scanning the conversation", () => {
    const { store, conversationId } = newFixture();
    seedExchanges(store, conversationId, 5);

    const plan = store
      .allRows(`EXPLAIN QUERY PLAN ${JOIN_PROBE_SQL}`, [conversationId])
      .map((row) => String(row.detail))
      .join("\n");

    // The revision side must be an equality seek on conversation_id AND turn_id.
    // Seeking on conversation_id alone is the quadratic walk this index removes.
    const revisionStep = plan
      .split("\n")
      .find((line) => line.includes("conversation_turn_revisions") || line.includes("revision"));
    expect(revisionStep, `no revision step in plan:\n${plan}`).toBeDefined();
    expect(revisionStep).toContain("conversation_turn_revisions_turn_id_idx");
    expect(revisionStep).toContain("turn_id=?");
  });

  it("returns the same turns in the same order as the unindexed query", () => {
    const { store, sessionId, conversationId } = newFixture();
    seedExchanges(store, conversationId, 6);

    const indexed = buildContextSnapshot(store, sessionId, OWNER, 10_000, SURFACE);
    const indexedTurns = indexed.recentTurns.map((turn) => `${turn.role}:${turn.content}`);

    // Drop the index and re-project: an additive index must not change results.
    store.execute("DROP INDEX conversation_turn_revisions_turn_id_idx");
    const unindexed = buildContextSnapshot(store, sessionId, OWNER, 10_000, SURFACE);

    expect(unindexed.recentTurns.map((turn) => `${turn.role}:${turn.content}`)).toEqual(indexedTurns);
    expect(indexedTurns.length).toBeGreaterThan(0);
  });

  it("creates the index on a database that predates the migration, and is idempotent on reopen", () => {
    const stateDir = newStateDir();
    const first = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    const indexRow = () =>
      first.allRows(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?",
        ["conversation_turn_revisions_turn_id_idx"],
      );
    expect(indexRow()).toHaveLength(1);

    // A store upgraded from a build without this migration: remove the index and
    // its version row, then reopen. The legacy principal must be migrated, not
    // rejected.
    first.execute("DROP INDEX conversation_turn_revisions_turn_id_idx");
    first.execute("DELETE FROM schema_migrations WHERE version = 33");
    expect(indexRow()).toHaveLength(0);

    const reopened = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    expect(
      reopened.allRows("SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?", [
        "conversation_turn_revisions_turn_id_idx",
      ]),
    ).toHaveLength(1);
    expect(
      reopened.allRows("SELECT version FROM schema_migrations WHERE version = 33", []),
    ).toHaveLength(1);

    // Already-migrated databases must reopen without re-running or throwing.
    const again = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    expect(
      again.allRows("SELECT version FROM schema_migrations WHERE version = 33", []),
    ).toHaveLength(1);
  });
});
