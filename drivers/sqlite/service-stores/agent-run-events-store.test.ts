import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import { createAgentRunEventSupervisor } from "../../../apps/service/chat/agent-run-events";
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
});
