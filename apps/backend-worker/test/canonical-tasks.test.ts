import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";
const { createServiceApp } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/app.ts",
    import.meta.url
  ).href
);
const { prepareTasksRead, resolveTasksWriteRecordId } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/composition/tasks-read.ts",
    import.meta.url
  ).href
);
const { createWriteFenceCounter } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/control/fence-counter.ts",
    import.meta.url
  ).href
);
const { createServedCounter } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/observability/served-count.ts",
    import.meta.url
  ).href
);
const { createWriteOpsCounter } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/observability/write-ops-counter.ts",
    import.meta.url
  ).href
);
const { registerTasksOpsRoutes } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/routes/tasks-ops.ts",
    import.meta.url
  ).href
);
const { registerTasksReadRoutes } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/routes/tasks-read.ts",
    import.meta.url
  ).href
);
const { createInMemoryStragglerTable } = await import(
  new URL(
    "../../../backends/example-platform/apps/service/stores/straggler-table.ts",
    import.meta.url
  ).href
);
const { SqliteAccountControlProjectionStore } = await import(
  new URL(
    "../../../backends/example-platform/drivers/sqlite/service-stores/projection-store.ts",
    import.meta.url
  ).href
);
const { SqliteTasksStore } = await import(
  new URL(
    "../../../backends/example-platform/drivers/sqlite/service-stores/tasks-store.ts",
    import.meta.url
  ).href
);
const { createSqliteWriteUnitOfWork } = await import(
  new URL(
    "../../../backends/example-platform/drivers/sqlite/service-stores/write-unit-of-work.ts",
    import.meta.url
  ).href
);
import { requestCanonicalTasks } from "../src/canonical-tasks";
import type { CanonicalService } from "../src/canonical-service";

const aliceToken = "test-firebase-alice";
const bobToken = "test-firebase-bob";
const content = {
  description: "Review canonical task",
  completed: false,
  completedAt: null,
  dueAt: null,
  owner: null,
  source: "manual",
  provenance: [],
  sortOrder: 0,
  indentLevel: 0,
  createdAt: 1,
  updatedAt: 1,
};

function fixture() {
  const db = new Database(":memory:");
  const control = new SqliteAccountControlProjectionStore(db);
  const tasks = new SqliteTasksStore(db);
  const stragglers = createInMemoryStragglerTable();
  const app = createServiceApp(() => new Response(null, { status: 404 }));
  const resolvePrincipal = (token: string) =>
    token === aliceToken
      ? { uid: "alice" }
      : token === bobToken
      ? { uid: "bob" }
      : null;
  const prepareRead = (principal: { uid: string }) =>
    prepareTasksRead({
      authorityBinding: { kind: "local_qa" },
      store: tasks,
      resolveAuthorization: () => ({
        owner_account_id: principal.uid,
        app_id: "test-app",
        key_id: "test-key",
      }),
      codecRootSecret: new Uint8Array(32).fill(1),
      cursorSigningKeyset: {
        active_key_id: "test-key",
        keys: [{ key_id: "test-key", secret: new Uint8Array(32).fill(2) }],
      },
      readTimestampEpochSeconds: 10,
      appliedFrontierState:
        tasks.listRecords(principal.uid).length === 0
          ? "no_applied_writes"
          : "caught_up",
    });
  registerTasksOpsRoutes(app, {
    resolvePrincipal,
    unitOfWork: createSqliteWriteUnitOfWork(db),
    stragglers,
    fence: {
      store: control,
      entitlement: { readEntitlement: () => null },
      counter: createWriteFenceCounter(),
    },
    counter: createWriteOpsCounter(),
    now: () => 10,
    resolveWriteRecordId: (principal: { uid: string }, id: string) =>
      resolveTasksWriteRecordId(
        prepareRead(principal).ports,
        principal.uid,
        id
      ),
  });
  registerTasksReadRoutes(app, {
    resolvePrincipal,
    prepareRead,
    fence: { store: control },
    counter: createServedCounter(),
  });
  const seen: { path: string; body: string; authorization: string | null }[] =
    [];
  const service: CanonicalService = {
    async fetch(request) {
      seen.push({
        path: new URL(request.url).pathname,
        body: await request.clone().text(),
        authorization: request.headers.get("authorization"),
      });
      return app.fetch(request);
    },
  };
  const activate = (accountId: string, epoch: number) => {
    const current = control.read(accountId);
    const observation = control.observe({
      account_id: accountId,
      control_revision: (current?.control_revision ?? 0) + 1,
      account_generation: "new",
      account_epoch: epoch,
      lifecycle_state: "active",
      deletion_epoch: null,
    });
    expect(observation.accepted).toBe(true);
    expect(
      control.activate(accountId, {
        epoch,
        at_control_revision: observation.projection.control_revision,
      }).activated
    ).toBe(true);
  };
  const caller = (token: string) => ({
    accountId: `firebase:${token === bobToken ? "bob" : "alice"}`,
    authorization: `Bearer ${token}`,
    stagingApiToken: "test-staging",
  });
  const post = (body: string, token = aliceToken) =>
    requestCanonicalTasks({
      service,
      caller: caller(token),
      method: "POST",
      body,
    });
  const read = (token = aliceToken) =>
    requestCanonicalTasks({
      service,
      caller: caller(token),
      method: "GET",
      query: new URLSearchParams(),
    });
  return { db, control, tasks, stragglers, activate, post, read, seen };
}

function envelope(writeId: string, epoch: number, op: object): string {
  return JSON.stringify({
    write_id: writeId.repeat(64),
    account_epoch: epoch,
    domain: "tasks",
    op,
  });
}

describe("canonical task authority delegation", () => {
  test("missing authority and staging credentials cannot produce an accepted write", async () => {
    let calls = 0;
    const service: CanonicalService = {
      async fetch() {
        calls += 1;
        throw new Error("Authority must not be called");
      },
    };
    for (const bound of [undefined, service]) {
      const response = await requestCanonicalTasks({
        service: bound,
        caller: {
          accountId: "firebase:alice",
          authorization: "Bearer test-staging",
          stagingApiToken: "test-staging",
        },
        method: "POST",
        body: envelope("a", 7, { op: "create", record_id: "task-1", content }),
      });
      expect(response.status).toBe(503);
      expect(await response.text()).toBe(
        '{"error":"maintenance","refusal_outcome":"control_unavailable"}'
      );
    }
    expect(calls).toBe(0);
  });

  test("unreadable GET pages are non-retryable projection_unavailable", async () => {
    const response = await requestCanonicalTasks({
      service: {
        async fetch() {
          return new Response('{"items":[]}', {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        },
      },
      caller: {
        accountId: "firebase:alice",
        authorization: `Bearer ${aliceToken}`,
        stagingApiToken: "test-staging",
      },
      method: "GET",
      query: new URLSearchParams(),
    });
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBeNull();
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "projection_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });

  test("canonical GET transport failures stay retryable", async () => {
    const response = await requestCanonicalTasks({
      service: {
        async fetch() {
          throw new Error("Authority unavailable");
        },
      },
      caller: {
        accountId: "firebase:alice",
        authorization: `Bearer ${aliceToken}`,
        stagingApiToken: "test-staging",
      },
      method: "GET",
      query: new URLSearchParams(),
    });
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).not.toBeNull();
    expect(await response.text()).toBe('{"error":"internal_server_error"}');
  });

  test.each([
    { status: 200, body: '{"success":true}' },
    {
      status: 200,
      body: '{"applied":{"record_id":"task-1","revision":null},"idempotent":false,"private":"secret"}',
    },
    {
      status: 409,
      body: '{"error":"stale_epoch","refusal_outcome":"stale_epoch","account_id":"other"}',
    },
  ])(
    "malformed success and private upstream errors are unavailable: %p",
    async (upstream) => {
      const response = await requestCanonicalTasks({
        service: {
          async fetch() {
            return new Response(upstream.body, {
              status: upstream.status,
              headers: { "content-type": "application/json" },
            });
          },
        },
        caller: {
          accountId: "firebase:alice",
          authorization: `Bearer ${aliceToken}`,
          stagingApiToken: "test-staging",
        },
        method: "POST",
        body: envelope("a", 7, { op: "create", record_id: "task-1", content }),
      });
      expect(response.status).toBe(503);
      expect(await response.text()).toBe(
        '{"error":"maintenance","refusal_outcome":"control_unavailable"}'
      );
    }
  );

  test("real route/UOW owns mutation, replay, conflict, read handles and account isolation", async () => {
    const f = fixture();
    try {
      f.activate("alice", 7);
      f.activate("bob", 7);
      const raw = envelope("a", 7, {
        op: "create",
        record_id: "task-1",
        content,
      });
      const first = await f.post(raw);
      expect(first.status).toBe(200);
      const applied = (await first.json()) as {
        applied: { revision: string };
        idempotent: boolean;
      };
      expect(applied.idempotent).toBe(false);
      expect(f.tasks.readRecord("alice", "task-1")?.content).toEqual(content);
      expect(f.tasks.readRecord("bob", "task-1")).toBeNull();
      expect((await (await f.post(raw)).json()) as unknown).toEqual({
        ...applied,
        idempotent: true,
      });
      expect(f.tasks.listRecords("alice")).toHaveLength(1);
      const reuse = await f.post(
        envelope("a", 7, { op: "create", record_id: "different", content })
      );
      expect(reuse.status).toBe(409);
      expect(await reuse.text()).toBe('{"error":"write_id_reuse"}');
      const read = await f.read();
      expect(read.status).toBe(200);
      const page = (await read.json()) as {
        accountEpoch: number;
        items: { id: string; revision: string; description: string }[];
      };
      expect(page.accountEpoch).toBe(7);
      expect(page.items).toHaveLength(1);
      expect(page.items[0]?.description).toBe(content.description);
      expect(page.items[0]?.revision).toBe(applied.applied.revision);
      const patch = envelope("b", 7, {
        op: "patch",
        record_id: page.items[0]!.id,
        base_revision: applied.applied.revision,
        patch: { completed: true },
      });
      expect((await f.post(patch)).status).toBe(200);
      expect(f.tasks.readRecord("alice", "task-1")?.content.completed).toBe(
        true
      );
      const conflict = await f.post(
        envelope("c", 7, {
          op: "patch",
          record_id: page.items[0]!.id,
          base_revision: applied.applied.revision,
          patch: { completed: false },
        })
      );
      expect(conflict.status).toBe(409);
      expect(await conflict.text()).toBe('{"error":"conflict"}');
      expect(
        ((await (await f.read(bobToken)).json()) as { items: unknown[] }).items
      ).toEqual([]);
      expect((await f.post(patch, bobToken)).status).toBe(409);
      expect(f.seen[0]).toEqual({
        path: "/v1/tasks/ops",
        body: raw,
        authorization: `Bearer ${aliceToken}`,
      });
    } finally {
      f.db.close();
    }
  });

  test("legacy missing control denies and advanced epoch rejects replay before registry while retaining envelope", async () => {
    const f = fixture();
    try {
      const raw = envelope("a", 7, {
        op: "create",
        record_id: "task-1",
        content,
      });
      const missing = await f.post(raw);
      expect(missing.status).toBe(503);
      expect(await missing.text()).toBe(
        '{"error":"maintenance","refusal_outcome":"control_unavailable"}'
      );
      expect(f.tasks.listRecords("alice")).toEqual([]);
      f.activate("alice", 7);
      expect((await f.post(raw)).status).toBe(200);
      f.activate("alice", 8);
      const stale = await f.post(raw);
      expect(stale.status).toBe(409);
      expect(await stale.text()).toBe(
        '{"error":"stale_epoch","refusal_outcome":"stale_epoch"}'
      );
      expect(f.stragglers.exportAccount("alice")[0]?.envelope_json).toBe(raw);
      expect(f.tasks.listRecords("alice")).toHaveLength(1);
    } finally {
      f.db.close();
    }
  });
});
