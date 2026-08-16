import { describe, expect, test } from "bun:test";

import { resolveTasksWriteRecordId, type TasksReadPorts } from "./tasks-read";

const opaque = (hexChar: string): string => `task1_${hexChar.repeat(64)}`;

const ports = (
  rows: readonly { readonly record_id: string; readonly handle: string }[],
): Pick<TasksReadPorts, "loadRecords" | "encodeItemRef"> => ({
  loadRecords: (accountId) => {
    if (accountId !== "acct") return [];
    return rows.map((row) => ({
      record_id: row.record_id,
      revision: "a".repeat(64),
      content: {},
      first_seen_seq: 1,
      last_applied_seq: 1,
    }));
  },
  encodeItemRef: (recordId) => {
    const row = rows.find((entry) => entry.record_id === recordId);
    return row === undefined ? opaque("0") : row.handle;
  },
});

describe("resolveTasksWriteRecordId", () => {
  test("a listed public handle maps onto the storage id, a storage id passes through, and an unmatched handle is null", () => {
    // red-proof: return the input HMAC unchanged. The write door then upserts
    // a second row keyed by the public id. APPLIED AND OBSERVED RED.
    const handle = opaque("a");
    const resolver = ports([{ record_id: "demo-task-cedar-shells", handle }]);
    expect(resolveTasksWriteRecordId(resolver, "acct", handle)).toBe("demo-task-cedar-shells");
    expect(resolveTasksWriteRecordId(resolver, "acct", "demo-task-cedar-shells"))
      .toBe("demo-task-cedar-shells");
    expect(resolveTasksWriteRecordId(resolver, "acct", opaque("c"))).toBeNull();
  });
});
