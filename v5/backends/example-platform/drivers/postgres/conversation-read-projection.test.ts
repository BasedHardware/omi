import { expect, test } from "bun:test";
import { parseConversationReadSnapshot } from "./conversation-read-projection";
import {
  prepareConversationsRead,
  readConversationsPage,
} from "../../apps/service/composition/conversations-read";

const row = (values: Record<string, unknown> = {}) => ({
  session_id: "11111111-2222-4333-8444-555555555555",
  conversation_id: "conversation-one",
  device: true,
  sequence: 1,
  started_at: "2026-09-01T10:00:00Z",
  ended_at: "2026-09-01T10:01:00Z",
  updated_at: "2026-09-01T10:02:00Z",
  state: "completed",
  excerpt: "Actual saved words",
  locked: true,
  source: "omi-device",
  ...values,
});

test("projects durable recording IDs and distinguishes transcript completion from pending memory work", () => {
  const projected = parseConversationReadSnapshot({
    revision: "7",
    records: [row()],
  });
  expect(projected.revision).toBe(7);
  expect(projected.records[0]?.record).toMatchObject({
    id: "recording:11111111-2222-4333-8444-555555555555",
    status: "processing",
    is_locked: true,
    structured: { title: "Actual saved words", overview: "Actual saved words" },
  });
  expect(
    parseConversationReadSnapshot({
      revision: 1,
      records: [row({ device: false, session_id: "listen-session" })],
    }).records[0]?.record.id
  ).toBe("conversation-one");
});

test("keeps queued and failed recordings visible and never publishes an unfinished provider result", () => {
  for (const state of ["queued", "running", "failed"]) {
    const record = parseConversationReadSnapshot({
      revision: 1,
      records: [row({ state, excerpt: "Not yet published", locked: false })],
    }).records[0]!.record;
    expect(record.structured).toEqual({ title: "Recording", overview: "" });
    expect(record.status).toBe(state === "failed" ? "failed" : "processing");
  }
  expect(
    parseConversationReadSnapshot({
      revision: 1,
      records: [row({ excerpt: "", locked: false })],
    }).records[0]?.record.status
  ).toBe("completed");
});

test("rejects corrupt, ambiguous, oversized or reordered snapshots instead of silently claiming a partial page", () => {
  for (const records of [
    [row({ state: "unknown" })],
    [row({ sequence: 0 })],
    [row({ excerpt: null })],
    [row({ ended_at: "bad" })],
    [row(), row({ sequence: 2 })],
    Array.from({ length: 10001 }, () => row()),
  ]) {
    expect(() =>
      parseConversationReadSnapshot({ revision: 1, records })
    ).toThrow();
  }
  const id = "recording:11111111-2222-4333-8444-555555555555";
  expect(() =>
    parseConversationReadSnapshot({
      revision: 1,
      records: [
        row(),
        row({
          device: false,
          session_id: "other",
          conversation_id: id,
          sequence: 2,
        }),
      ],
    })
  ).toThrow();
});

test("device capture provenance survives the canonical page without replacing server lifecycle times", () => {
  for (const capturedAtMs of [undefined, null, 0, 8640000000000000]) {
    const snapshot = parseConversationReadSnapshot({
      revision: 1,
      records: [row({ captured_at_ms: capturedAtMs })],
    });
    const prepared = prepareConversationsRead({
      store: {
        listOrderedRecords: () => snapshot.records,
        readStateRevision: () => snapshot.revision,
      },
      authorityBinding: { kind: "local_qa" },
      resolveAuthorization: () => ({
        owner_account_id: "owner",
        app_id: "app",
        key_id: "key",
      }),
      codecRootSecret: new Uint8Array(32).fill(1),
      cursorSigningKeyset: {
        active_key_id: "test",
        keys: [{ key_id: "test", secret: new Uint8Array(32).fill(2) }],
      },
      readTimestampEpochSeconds: 100,
      appliedFrontierState: "caught_up",
    });
    const item = JSON.parse(
      readConversationsPage({ limit: 25, cursor: null }, prepared)
        .canonical_json
    ).items[0];
    expect(item.startedAt).toBe(Date.parse(row().started_at));
    expect(item.finishedAt).toBe(Date.parse(row().ended_at));
    if (capturedAtMs == null) expect(item).not.toHaveProperty("capturedAtMs");
    else expect(item.capturedAtMs).toBe(capturedAtMs);
  }
  for (const captured_at_ms of [-1, 0.5, true, NaN, Infinity, 8640000000000001])
    expect(() =>
      parseConversationReadSnapshot({
        revision: 1,
        records: [row({ captured_at_ms })],
      })
    ).toThrow();
  expect(() =>
    parseConversationReadSnapshot({
      revision: 1,
      records: [
        row({ device: false, session_id: "listen", captured_at_ms: 1 }),
      ],
    })
  ).toThrow();
});
