import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  createAgentRunEventSupervisor,
  type AgentRunEventStore,
} from "../../../apps/service/chat/agent-run-events";
import { createSqliteAgentRunEventStore } from "./agent-run-events-store";

const RUN = "generation-sqlite";
const ATTEMPT = `${RUN}:attempt:1`;

const seed = (store: ReturnType<typeof createSqliteAgentRunEventStore>) => {
  const supervisor = createAgentRunEventSupervisor({
    events: store,
    nowEpochMilliseconds: () => 1_786_352_400_000,
    eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
  });
  supervisor.accepted({ runId: RUN, attemptId: ATTEMPT, admissionId: "admission-sqlite" });
  supervisor.status({ runId: RUN, attemptId: ATTEMPT, status: "generating", progressPct: 10 });
  supervisor.terminal({ runId: RUN, attemptId: ATTEMPT, terminalOutcome: "failed",
    terminalCode: "generation_provider_failed", retryable: true, recoveryAction: null });
};

describe("SQLite AgentRunEventStore", () => {
  test("persists exact ordered events and cursor identity across reconstruction", () => {
    const db = new Database(":memory:");
    const first = createSqliteAgentRunEventStore(db);
    seed(first);
    const before = first.list(RUN);
    const second = createSqliteAgentRunEventStore(db);
    expect(second.list(RUN)).toEqual(before);
    expect(second.snapshot()).toEqual(first.snapshot());
    const cursor = before[1]!.eventId;
    expect(second.list(RUN).find((event) => event.eventId === cursor)?.sequence).toBe(2);
    db.close();
  });

  test("fails closed on corrupt JSON and run/sequence identity instead of dropping rows", () => {
    const db = new Database(":memory:");
    const store = createSqliteAgentRunEventStore(db);
    seed(store);
    db.query("UPDATE service_agent_run_events SET event_json = ? WHERE run_id = ? AND sequence = ?")
      .run("{not-json", RUN, 2);
    expect(() => store.list(RUN)).toThrow("corrupt agent run event JSON");
    expect(() => createSqliteAgentRunEventStore(db)).toThrow("corrupt agent run event JSON");
    db.close();
  });

  test("rejects cross-run rows whose event payload does not match the durable key", () => {
    const db = new Database(":memory:");
    const store = createSqliteAgentRunEventStore(db);
    seed(store);
    const event = store.list(RUN)[0]!;
    db.query("UPDATE service_agent_run_events SET event_json = ? WHERE run_id = ? AND sequence = ?")
      .run(JSON.stringify({ ...event, runId: "foreign-run" }), RUN, 1);
    expect(() => store.snapshot()).toThrow("corrupt agent run event row");
    db.close();
  });

  test("constructor restores every run and rejects sequence gaps or terminal-order corruption", () => {
    const db = new Database(":memory:");
    const store = createSqliteAgentRunEventStore(db);
    seed(store);
    const status = store.list(RUN)[1]!;
    db.query("UPDATE service_agent_run_events SET sequence = ? WHERE run_id = ? AND sequence = ?")
      .run(4, RUN, 2);
    db.query("UPDATE service_agent_run_events SET event_json = ? WHERE run_id = ? AND sequence = ?")
      .run(JSON.stringify({ ...status, sequence: 4 }), RUN, 4);
    expect(() => createSqliteAgentRunEventStore(db)).toThrow("invalid agent run snapshot");
    db.query("UPDATE service_agent_run_events SET sequence = ? WHERE run_id = ? AND sequence = ?")
      .run(2, RUN, 4);
    db.query("UPDATE service_agent_run_events SET event_json = ? WHERE run_id = ? AND sequence = ?")
      .run(JSON.stringify({ ...status, sequence: 2 }), RUN, 2);
    // The rows are restored to their original valid sequence before injecting
    // a post-terminal status, which the constructor must also reject.
    db.query(`
      INSERT INTO service_agent_run_events (run_id, event_id, sequence, event_json)
      VALUES (?, ?, ?, ?)
    `).run(RUN, `${RUN}:event:4:status`, 4, JSON.stringify({
      schemaVersion: 1,
      runId: RUN,
      attemptId: ATTEMPT,
      eventId: `${RUN}:event:4:status`,
      sequence: 4,
      visibility: "ui",
      createdAt: 1_786_352_400_000,
      safeSummary: "status",
      kind: "status",
      status: "generating",
      progressPct: 20,
    }));
    expect(() => createSqliteAgentRunEventStore(db)).toThrow("invalid agent run snapshot terminal");
    db.close();
  });

  test("immediate cross-connection writers preserve one ordered lifecycle without loss", async () => {
    const directory = mkdtempSync(join(tmpdir(), "omi-agent-events-writers-"));
    const path = join(directory, "service.sqlite");
    const firstDb = new Database(path);
    const secondDb = new Database(path);
    try {
      const first = createSqliteAgentRunEventStore(firstDb);
      const second = createSqliteAgentRunEventStore(secondDb);
      const acceptedSupervisor = createAgentRunEventSupervisor({
        events: first,
        nowEpochMilliseconds: () => 1_786_352_400_000,
        eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
      });
      acceptedSupervisor.accepted({ runId: RUN, attemptId: ATTEMPT, admissionId: "admission-sqlite" });
      // Hold both supervisors on the same pre-write cursor to model two
      // processes that read before either writer enters its immediate append.
      // The second writer must retry with a new sequence and event id after the
      // first transaction commits, rather than dropping its distinct status.
      const stale = first.list(RUN);
      const staleView = (store: AgentRunEventStore): AgentRunEventStore => {
        let reads = 0;
        return {
          append: (input) => store.append(input),
          list: (runId) => reads++ === 0 ? stale : store.list(runId),
          snapshot: () => store.snapshot(),
          restore: (snapshot) => store.restore(snapshot),
          reset: () => store.reset(),
        };
      };
      const firstSupervisor = createAgentRunEventSupervisor({
        events: staleView(first),
        nowEpochMilliseconds: () => 1_786_352_400_000,
        eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
      });
      const secondSupervisor = createAgentRunEventSupervisor({
        events: staleView(second),
        nowEpochMilliseconds: () => 1_786_352_400_000,
        eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
      });
      await Promise.all([
        Promise.resolve().then(() => firstSupervisor.status({
          runId: RUN, attemptId: ATTEMPT, status: "generating", progressPct: 10,
        })),
        Promise.resolve().then(() => secondSupervisor.status({
          runId: RUN, attemptId: ATTEMPT, status: "generating", progressPct: 20,
        })),
      ]);
      const events = first.list(RUN);
      expect(events.map((event) => event.sequence)).toEqual([1, 2, 3]);
      expect(new Set(events.map((event) => event.eventId)).size).toBe(3);
      expect(events.filter((event) => event.kind === "status")).toHaveLength(2);
      expect(events.filter((event) => event.kind === "status").map((event) => event.progressPct))
        .toEqual([10, 20]);

      // Repeating an identical stale write remains an idempotent replay, not a
      // fourth status event.
      const replay = createAgentRunEventSupervisor({
        events: staleView(first),
        nowEpochMilliseconds: () => 1_786_352_400_000,
        eventId: (runId, sequence, kind) => `${runId}:event:${sequence}:${kind}`,
      }).status({ runId: RUN, attemptId: ATTEMPT, status: "generating", progressPct: 10 });
      expect(replay.eventId).toBe(events[1]!.eventId);
      expect(first.list(RUN)).toHaveLength(3);
    } finally {
      secondDb.close();
      firstDb.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
