/**
 * Binding proofs for the account epoch served by `GET /v1/tasks`.
 *
 * These tests keep the three conditions from AUDIT-adr012-epoch-check.md
 * executable: refusals do not vary with control state, request-supplied account
 * identifiers are never consulted, and a success reads the authenticated
 * account from the write fence's existing projection store.
 */

import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";
import { Hono } from "hono";

import {
  parseTaskPageJson,
  readTaskPageAccountEpoch,
  type TaskRead,
} from "@omi-core/ratified-contracts/projections/tasks";

import type { AccountControlObservation } from "../../../core/control/account-control";
import { ApplicationReadDenied } from "../../../core/retrieve/authorization-boundary";
import type { DevPrincipal } from "../auth/dev-token";
import { prepareTasksRead, type PreparedTasksRead } from "../composition/tasks-read";
import { createWriteFenceCounter } from "./fence-counter";
import {
  createInMemoryAccountControlProjectionStore,
  type AccountControlProjectionStore,
} from "./projection-store";
import { applyWriteFence } from "./write-fence-guard";
import { createLocalService } from "../app-facing";
import { createServedCounter } from "../observability/served-count";
import { registerTasksReadRoutes, TASKS_READ_PATH } from "../routes/tasks-read";
import { createInMemoryTasksStore } from "../stores/tasks-store";

const ACCOUNT_A = "acct-epoch-a";
const ACCOUNT_B = "acct-epoch-b";
const ACCOUNT_WITHOUT_PROJECTION = "acct-epoch-absent";
const TOKEN_A = "token-a";
const TOKEN_B = "token-b";
const TOKEN_WITHOUT_PROJECTION = "token-absent";
const FIXED_NOW = 1_786_000_000;

type ReadOutcome = "ok" | "denied" | "failed";

interface Booted {
  readonly app: Hono;
  readonly store: AccountControlProjectionStore;
  readonly storeReads: string[];
}

const observation = (
  accountId: string,
  overrides: Partial<AccountControlObservation> = {},
): AccountControlObservation => ({
  account_id: accountId,
  control_revision: 1,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  ...overrides,
});

const seedEpoch = (
  store: AccountControlProjectionStore,
  accountId: string,
  epoch: number,
): void => {
  expect(store.observe(observation(accountId)).accepted).toBe(true);
  expect(store.observe(observation(accountId, {
    control_revision: 2,
    account_generation: "migrating",
  })).accepted).toBe(true);
  expect(store.observe(observation(accountId, {
    control_revision: 3,
    account_generation: "new",
    account_epoch: epoch,
  })).accepted).toBe(true);
  expect(store.activate(accountId, { epoch, at_control_revision: 3 }).activated).toBe(true);
};

const recordingStore = (): {
  readonly store: AccountControlProjectionStore;
  readonly reads: string[];
} => {
  const delegate = createInMemoryAccountControlProjectionStore();
  const reads: string[] = [];
  return {
    reads,
    store: Object.freeze({
      read(accountId) {
        reads.push(accountId);
        return delegate.read(accountId);
      },
      observe: (value) => delegate.observe(value),
      activate: (accountId, request) => delegate.activate(accountId, request),
      deactivate: (accountId) => delegate.deactivate(accountId),
      forget: (accountId) => delegate.forget(accountId),
      reconcile: (value, operator) => delegate.reconcile(value, operator),
    }),
  };
};

const preparedRead = (principal: DevPrincipal): PreparedTasksRead => {
  const tasks = createInMemoryTasksStore();
  return prepareTasksRead({
    store: tasks,
    resolveAuthorization: () => ({
      owner_account_id: principal.uid,
      app_id: "epoch-proof-app",
      key_id: "epoch-proof-key",
    }),
    codecRootSecret: new Uint8Array(32).fill(17),
    cursorSigningKeyset: {
      active_key_id: "epoch-proof-key",
      keys: [{ key_id: "epoch-proof-key", secret: new Uint8Array(32).fill(29) }],
    },
    readTimestampEpochSeconds: FIXED_NOW,
    appliedFrontierState: "no_applied_writes",
  });
};

const boot = (input: {
  readonly epochs?: Readonly<Record<string, number>>;
  readonly outcome?: ReadOutcome;
} = {}): Booted => {
  const recorded = recordingStore();
  for (const [accountId, epoch] of Object.entries(input.epochs ?? {})) {
    seedEpoch(recorded.store, accountId, epoch);
  }

  const principals = new Map<string, DevPrincipal>([
    [TOKEN_A, { uid: ACCOUNT_A }],
    [TOKEN_B, { uid: ACCOUNT_B }],
    [TOKEN_WITHOUT_PROJECTION, { uid: ACCOUNT_WITHOUT_PROJECTION }],
  ]);
  const app = new Hono({ strict: true });
  registerTasksReadRoutes(app, {
    resolvePrincipal: (token) => principals.get(token) ?? null,
    prepareRead: (principal) => {
      if (input.outcome === "denied") throw new ApplicationReadDenied("missing_scope");
      if (input.outcome === "failed") throw new Error("fixed test failure");
      return preparedRead(principal);
    },
    fence: { store: recorded.store },
    counter: createServedCounter(),
  });
  app.notFound(() => new Response(JSON.stringify({ error: "not_found" }), {
    status: 404,
    headers: { "cache-control": "no-store", "content-type": "application/json" },
  }));
  return { app, store: recorded.store, storeReads: recorded.reads };
};

const auth = (token: string): Record<string, string> => ({ authorization: `Bearer ${token}` });

interface CapturedResponse {
  readonly status: number;
  readonly headers: readonly [string, string][];
  readonly body: string;
}

const capture = async (response: Response): Promise<CapturedResponse> => ({
  status: response.status,
  headers: [...response.headers.entries()].sort(([left], [right]) => left.localeCompare(right)),
  body: await response.text(),
});

const pageFrom = async (response: Response): Promise<TaskRead.Page> => {
  expect(response.status).toBe(200);
  const page = parseTaskPageJson(await response.text());
  expect(page).not.toBeNull();
  return page!;
};

describe("tasks read account epoch — binding proofs", () => {
  test("every refusal is epoch-independent across absent and non-null control projections", async () => {
    const epoch = 830_619;
    const cases: readonly {
      readonly name: string;
      readonly outcome?: ReadOutcome;
      readonly path: string;
      readonly init?: RequestInit;
      readonly expectedStatus: number;
    }[] = [
      { name: "401", path: TASKS_READ_PATH, expectedStatus: 401 },
      { name: "403", outcome: "denied", path: TASKS_READ_PATH, init: { headers: auth(TOKEN_A) }, expectedStatus: 403 },
      { name: "400", path: `${TASKS_READ_PATH}?limit=0`, init: { headers: auth(TOKEN_A) }, expectedStatus: 400 },
      { name: "404", path: "/v1/not-a-route", init: { headers: auth(TOKEN_A) }, expectedStatus: 404 },
      { name: "500", outcome: "failed", path: TASKS_READ_PATH, init: { headers: auth(TOKEN_A) }, expectedStatus: 500 },
      { name: "trailing slash", path: `${TASKS_READ_PATH}/`, init: { headers: auth(TOKEN_A) }, expectedStatus: 404 },
      { name: "duplicate parameter", path: `${TASKS_READ_PATH}?limit=1&limit=2`, init: { headers: auth(TOKEN_A) }, expectedStatus: 400 },
      { name: "wrong method", path: TASKS_READ_PATH, init: { method: "POST", headers: auth(TOKEN_A) }, expectedStatus: 404 },
    ];

    const unknownAbsent = await capture(await boot().app.request("/v1/not-a-route"));
    const unknownSeeded = await capture(await boot({ epochs: { [ACCOUNT_A]: epoch } })
      .app.request("/v1/not-a-route"));
    expect(unknownSeeded).toEqual(unknownAbsent);

    for (const scenario of cases) {
      const absent = boot({ outcome: scenario.outcome });
      const seeded = boot({ epochs: { [ACCOUNT_A]: epoch }, outcome: scenario.outcome });
      const absentResponse = await capture(await absent.app.request(scenario.path, scenario.init));
      const seededResponse = await capture(await seeded.app.request(scenario.path, scenario.init));

      expect({ name: scenario.name, status: absentResponse.status })
        .toEqual({ name: scenario.name, status: scenario.expectedStatus });
      expect(seededResponse).toEqual(absentResponse);
      expect(absentResponse.body.toLowerCase()).not.toContain("epoch");
      expect(absentResponse.body).not.toContain(String(epoch));
      if (scenario.expectedStatus === 404) expect(absentResponse).toEqual(unknownAbsent);
    }
  });

  test("body, query, and non-Authorization headers cannot select an account", async () => {
    const epochA = 17;
    const epochB = 91;
    const local = boot({ epochs: { [ACCOUNT_A]: epochA, [ACCOUNT_B]: epochB } });
    local.storeReads.length = 0;

    const requests: readonly [string, RequestInit?][] = [
      [TASKS_READ_PATH],
      [`${TASKS_READ_PATH}?account_id=${ACCOUNT_B}`],
      [`${TASKS_READ_PATH}?accountId=${ACCOUNT_B}`],
      [TASKS_READ_PATH, { headers: { ...auth(TOKEN_A), account_id: ACCOUNT_B } }],
      [TASKS_READ_PATH, { headers: { ...auth(TOKEN_A), "x-account-id": ACCOUNT_B } }],
    ];
    for (const [path, init] of requests) {
      const page = await pageFrom(await local.app.request(path, {
        ...init,
        headers: { ...auth(TOKEN_A), ...(init?.headers ?? {}) },
      }));
      expect(readTaskPageAccountEpoch(page)).toBe(epochA);
    }

    const readsBeforeBody = local.storeReads.length;
    const bodyAttempt = await local.app.request(TASKS_READ_PATH, {
      method: "POST",
      headers: { ...auth(TOKEN_A), "content-type": "application/json" },
      body: JSON.stringify({ account_id: ACCOUNT_B }),
    });
    expect(bodyAttempt.status).toBe(404);
    expect(local.storeReads.length).toBe(readsBeforeBody);
    expect(local.storeReads).toEqual(Array(requests.length).fill(ACCOUNT_A));
    expect(local.storeReads).not.toContain(ACCOUNT_B);
  });

  test("the authenticated account reads its own epoch from the write fence's store", async () => {
    // Put two authenticated accounts behind ONE route and ONE projection
    // store. Epoch zero is deliberate: presence must decide, not truthiness.
    const local = boot({ epochs: { [ACCOUNT_A]: 0, [ACCOUNT_B]: 29 } });
    const fenceCounter = createWriteFenceCounter();
    expect(applyWriteFence(
      { store: local.store, entitlement: { readEntitlement: () => null }, counter: fenceCounter },
      { accountId: ACCOUNT_A, requestEpoch: 0, runId: "epoch-a" },
    )).toEqual({ admitted: true, account_epoch: 0 });
    expect(applyWriteFence(
      { store: local.store, entitlement: { readEntitlement: () => null }, counter: fenceCounter },
      { accountId: ACCOUNT_B, requestEpoch: 29, runId: "epoch-b" },
    )).toEqual({ admitted: true, account_epoch: 29 });
    local.storeReads.length = 0;

    const pageA = await pageFrom(await local.app.request(TASKS_READ_PATH, { headers: auth(TOKEN_A) }));
    const pageB = await pageFrom(await local.app.request(TASKS_READ_PATH, { headers: auth(TOKEN_B) }));
    expect(Object.hasOwn(pageA, "accountEpoch")).toBe(true);
    expect(readTaskPageAccountEpoch(pageA)).toBe(0);
    expect(readTaskPageAccountEpoch(pageB)).toBe(29);
    expect(local.storeReads).toEqual([ACCOUNT_A, ACCOUNT_B]);

    const absentPage = await pageFrom(await local.app.request(TASKS_READ_PATH, {
      headers: auth(TOKEN_WITHOUT_PROJECTION),
    }));
    expect(Object.hasOwn(absentPage, "accountEpoch")).toBe(false);
    expect(readTaskPageAccountEpoch(absentPage)).toBeNull();
    expect(local.storeReads).toEqual([ACCOUNT_A, ACCOUNT_B, ACCOUNT_WITHOUT_PROJECTION]);

    // Finally pin the REAL registered composition: QA control and the tasks
    // read route must see the same store created by `createLocalService`.
    const real = createLocalService({
      db: new Database(":memory:"),
      ownerAccountId: ACCOUNT_A,
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "tasks-read-account-epoch-real-composition",
    });
    seedEpoch(real.writePath.control, ACCOUNT_A, 43);
    const realPage = await pageFrom(await real.app.request(TASKS_READ_PATH, {
      headers: auth(real.devToken),
    }));
    expect(readTaskPageAccountEpoch(realPage)).toBe(43);
  });
});
