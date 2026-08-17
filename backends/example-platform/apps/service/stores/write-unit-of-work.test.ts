// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import { expect, test } from "bun:test";

import { createInMemoryTasksStore } from "./tasks-store";
import { createInMemoryWriteIdRegistry } from "./write-id-registry";
import { createInMemoryWriteUnitOfWork } from "./write-unit-of-work";

test("the in-memory composition implements the same indivisible write operation", async () => {
  const tasks = createInMemoryTasksStore();
  const registry = createInMemoryWriteIdRegistry();
  const unitOfWork = createInMemoryWriteUnitOfWork(tasks, registry);
  const input = {
    accountId: "acct-memory-unit",
    writeId: "17".repeat(32),
    fingerprintOf: {
      account_epoch: 7,
      domain: "tasks",
      op: { op: "create", record_id: "one", content: { value: 1 } },
    },
    accountEpoch: 7,
    op: { op: "create" as const, record_id: "one", content: { value: 1 } },
  };

  const first = await unitOfWork.execute(input);
  const replay = await unitOfWork.execute(input);

  expect(first.kind).toBe("applied");
  expect(replay).toEqual(first.kind === "applied"
    ? { kind: "replay", outcome: first.outcome }
    : null);
  expect(tasks.listRecords(input.accountId)).toHaveLength(1);
  expect(registry.size(input.accountId)).toBe(1);
});
